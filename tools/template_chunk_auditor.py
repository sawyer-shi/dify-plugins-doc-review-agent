from collections.abc import Generator
from typing import Any
import json

from dify_plugin import Tool
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.utils import detect_text_language, dual_messages, invoke_llm, safe_json_load, strip_model_thoughts


class TemplateChunkAuditorTool(Tool):
    @staticmethod
    def _candidate_indices(idx: int, total: int) -> list[int]:
        candidates: list[int] = []
        for cand in [idx, idx - 1, idx + 1]:
            if 0 <= cand < total and cand not in candidates:
                candidates.append(cand)
        return candidates

    @staticmethod
    def _normalize_quote(quote: str) -> str:
        return " ".join(str(quote or "").split())

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
            candidate_idx_list = self._candidate_indices(idx, len(doc_chunks))
            candidate_chunks = [doc_chunks[c] for c in candidate_idx_list]

            default_chunk = candidate_chunks[0] if candidate_chunks else {}
            template_code = f"template-{idx + 1:04d}"
            template_name = str(template_chunk.get("title", "")).strip() or f"Template Chunk {idx + 1:03d}"

            candidates_block = []
            for cand_pos, cand_idx in enumerate(candidate_idx_list):
                cand = doc_chunks[cand_idx]
                candidates_block.append(
                    f"- candidate_pos: {cand_pos}\n"
                    f"  source_index: {cand_idx}\n"
                    f"  chunk_id: {cand.get('chunk_id', cand_idx)}\n"
                    f"  text: {str(cand.get('text', '')).strip()}"
                )
            candidates_text = "\n".join(candidates_block) if candidates_block else "- candidate_pos: 0\n  source_index: -1\n  chunk_id: -1\n  text: "

            prompt = f"""
You are a senior legal reviewer.

Extra hint: {extra_hint}

Template chunk (baseline):
- template_code: {template_code}
- template_name: {template_name}
- text: {template_text}

Document chunk candidates to audit (ordered by priority):
{candidates_text}

Task:
Compare candidate document chunks against the template chunk and find non-compliance findings.
First choose the best matched candidate for anchoring comments, then return one or more findings.
Assess severity automatically as high/medium/low according to legal/commercial impact.
Return JSON only:
{{
  "matched_candidate_pos": 0,
  "items": [
    {{
      "severity": "high|medium|low",
      "quote": "snippet from chosen document chunk, can be empty if missing",
      "reason": "why non-compliant based on template",
      "suggestion": "how to align with template"
    }}
  ]
}}

Requirements:
1) Use template chunk as the baseline.
2) If one candidate is missing or deviates materially, include finding items.
3) quote should come from chosen candidate when available; if missing from document, quote can be empty.
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

            matched_pos = one.get("matched_candidate_pos", 0)
            try:
                matched_pos_int = int(matched_pos)
            except Exception:
                matched_pos_int = 0
            if matched_pos_int < 0 or matched_pos_int >= len(candidate_chunks):
                matched_pos_int = 0

            doc_chunk = candidate_chunks[matched_pos_int] if candidate_chunks else default_chunk
            doc_text = str(doc_chunk.get("text", "")).strip()

            items = one.get("items") if isinstance(one.get("items"), list) else []
            if not items:
                continue

            for finding in items:
                if not isinstance(finding, dict):
                    continue

                severity = str(finding.get("severity", "")).strip().lower()
                if severity not in ["high", "medium", "low"]:
                    severity = "medium"

                quote = self._normalize_quote(str(finding.get("quote", "")).strip())
                if quote and doc_text and quote not in doc_text:
                    quote = ""

                reason = str(finding.get("reason", "")).strip()
                suggestion = str(finding.get("suggestion", "")).strip()
                if not reason and not suggestion:
                    continue

                seq_no += 1
                template_code = f"template-{seq_no:04d}"

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
                        "reason": reason,
                        "suggestion": suggestion,
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
