from collections.abc import Generator
from typing import Any
import json

from dify_plugin import Tool
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.utils import detect_text_language, dual_messages, invoke_llm, safe_json_load, strip_model_thoughts


class TemplateChunkAuditorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        template_slices_text = tool_parameters.get("template_slices_text") or ""
        doc_slices_text = tool_parameters.get("doc_slices_text") or ""
        extra_hint = tool_parameters.get("extra_hint") or ""
        output_language = str(tool_parameters.get("output_language") or "auto").strip().lower()

        if not isinstance(llm_model, dict):
            for m in dual_messages(self, "Error: model_config invalid.", {"error": "model_config invalid"}):
                yield m
            return

        template_payload = template_slices_text if isinstance(template_slices_text, dict) else safe_json_load(template_slices_text, None)
        doc_payload = doc_slices_text if isinstance(doc_slices_text, dict) else safe_json_load(doc_slices_text, None)

        if not isinstance(template_payload, dict) or not isinstance(template_payload.get("chunks"), list):
            for m in dual_messages(self, "Error: template_slices_text must be JSON with chunks list.", {"error": "Invalid template_slices_text"}):
                yield m
            return
        if not isinstance(doc_payload, dict) or not isinstance(doc_payload.get("chunks"), list):
            for m in dual_messages(self, "Error: doc_slices_text must be JSON with chunks list.", {"error": "Invalid doc_slices_text"}):
                yield m
            return

        template_chunks = template_payload.get("chunks", [])
        doc_chunks = doc_payload.get("chunks", [])

        if output_language == "auto":
            lang_sample = "\n".join(str(c.get("text", "")) for c in doc_chunks[:8])
            output_language = detect_text_language(lang_sample)
        if output_language not in ["zh", "en", "ja", "ko", "es", "fr", "de", "pt", "ru", "ar"]:
            output_language = "en"

        audit_results: list[dict[str, Any]] = []
        seq_no = 0
        total_pairs = 0

        for idx, template_chunk in enumerate(template_chunks):
            template_text = str(template_chunk.get("text", "")).strip()
            if not template_text:
                continue

            total_pairs += 1
            doc_chunk = doc_chunks[idx] if idx < len(doc_chunks) else {}
            doc_text = str(doc_chunk.get("text", "")).strip()
            seq_no += 1
            template_code = f"template-{seq_no:04d}"
            template_name = str(template_chunk.get("title", "")).strip() or f"范本切片{seq_no:03d}"

            prompt = f"""
You are a senior legal reviewer.

Extra hint: {extra_hint}

Template chunk (baseline):
- template_code: {template_code}
- template_name: {template_name}
- text: {template_text}

Document chunk to audit:
- chunk_id: {doc_chunk.get("chunk_id", idx)}
- text: {doc_text}

Task:
Compare the document chunk against the template chunk and decide whether it is non-compliant.
Assess severity automatically as high/medium/low according to legal/commercial impact.
Return JSON only:
{{
  "hit": true|false,
  "severity": "high|medium|low",
  "quote": "exact snippet from document chunk",
  "reason": "why non-compliant based on template",
  "suggestion": "how to align with template"
}}

Requirements:
1) Use template chunk as the baseline.
2) If document chunk is missing or deviates materially, set hit=true.
3) quote must come from document chunk when available; if document chunk is empty, quote can be empty.
4) reason and suggestion language must be {output_language}.
5) Output JSON only.
"""

            try:
                model_output = invoke_llm(self, llm_model, [UserPromptMessage(content=prompt)])
            except Exception as e:
                for m in dual_messages(self, f"LLM Error: {str(e)}", {"error": f"LLM Error: {str(e)}"}):
                    yield m
                return

            one = safe_json_load(strip_model_thoughts(model_output), {})
            if not isinstance(one, dict):
                for m in dual_messages(self, "Error: Invalid JSON from template chunk auditor model.", {"error": "Invalid JSON from template chunk auditor model"}):
                    yield m
                return
            if not bool(one.get("hit")):
                continue

            quote = str(one.get("quote", "")).strip()
            if quote and doc_text and quote not in doc_text:
                continue
            if "\n" in quote or "\r" in quote:
                continue

            severity = str(one.get("severity", "")).strip().lower()
            if severity not in ["high", "medium", "low"]:
                severity = "medium"

            audit_results.append(
                {
                    "chunk_id": doc_chunk.get("chunk_id", idx),
                    "chunk_hash": str(doc_chunk.get("chunk_hash", "")),
                    "element_refs": doc_chunk.get("element_refs", []),
                    "element_meta": doc_chunk.get("element_meta", []),
                    "matched_rule_code": template_code,
                    "matched_rule_name": template_name,
                    "rule_level": "medium",
                    "severity": severity,
                    "quote": quote,
                    "reason": str(one.get("reason", "")).strip(),
                    "suggestion": str(one.get("suggestion", "")).strip(),
                }
            )

        payload = {
            "audit_results": audit_results,
            "total_pairs": total_pairs,
            "total_hits": len(audit_results),
            "output_language": output_language,
        }
        out_text = json.dumps(payload, ensure_ascii=False)
        for m in dual_messages(self, out_text, payload):
            yield m
