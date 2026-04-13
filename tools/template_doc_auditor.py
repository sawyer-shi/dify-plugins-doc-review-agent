from collections.abc import Generator
from typing import Any
import json

from dify_plugin import Tool
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.utils import detect_text_language, dual_messages, invoke_llm, safe_json_load, strip_model_thoughts


class TemplateDocAuditorTool(Tool):
    @staticmethod
    def _normalize_quote(quote: str) -> str:
        return " ".join(str(quote or "").split())

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        template_text = str(tool_parameters.get("template_text") or "")
        doc_text = str(tool_parameters.get("doc_text") or "")
        chunk_id = tool_parameters.get("chunk_id", 0)
        chunk_hash = str(tool_parameters.get("chunk_hash") or "")
        element_refs = tool_parameters.get("element_refs") or []
        element_meta = tool_parameters.get("element_meta") or []
        extra_hint = str(tool_parameters.get("extra_hint") or "")
        output_language = str(tool_parameters.get("output_language") or "auto").strip().lower()

        if not isinstance(llm_model, dict):
            for m in dual_messages(self, "Error: model_config invalid.", {"error": "model_config invalid"}):
                yield m
            return
        if not template_text.strip():
            payload = {"audit_results": [], "total_pairs": 0, "total_hits": 0}
            for m in dual_messages(self, json.dumps(payload, ensure_ascii=False), payload):
                yield m
            return

        if output_language == "auto":
            output_language = detect_text_language(doc_text)
        if output_language not in ["zh", "en", "ja", "ko", "es", "fr", "de", "pt", "ru", "ar"]:
            output_language = "en"

        prompt = f"""
You are a senior legal reviewer.

Extra hint: {extra_hint}

Template full text (baseline):
{template_text}

Document full text to audit:
{doc_text}

Task:
Find non-compliant places in the document by using the template as baseline.
Assess severity automatically as high/medium/low according to legal/commercial impact.
Return JSON only:
{{
  "items": [
    {{
      "severity": "high|medium|low",
      "quote": "exact snippet from document",
      "reason": "why non-compliant based on template",
      "suggestion": "how to align with template"
    }}
  ]
}}

Requirements:
1) Only list meaningful non-compliance findings.
2) quote should be exact snippet from document whenever possible; if a required template clause is fully missing, quote can be empty.
3) reason and suggestion language must be {output_language}.
4) Output JSON only.
"""

        try:
            model_output = invoke_llm(self, llm_model, [UserPromptMessage(content=prompt)])
        except Exception as e:
            for m in dual_messages(self, f"LLM Error: {str(e)}", {"error": f"LLM Error: {str(e)}"}):
                yield m
            return

        payload = safe_json_load(strip_model_thoughts(model_output), {})
        if not isinstance(payload, dict):
            for m in dual_messages(self, "Error: Invalid JSON from template auditor model.", {"error": "Invalid JSON from template auditor model"}):
                yield m
            return

        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        audit_results: list[dict[str, Any]] = []

        for idx, one in enumerate(items, start=1):
            if not isinstance(one, dict):
                continue
            quote = self._normalize_quote(str(one.get("quote", "")).strip())
            if quote and doc_text and quote not in doc_text:
                quote = ""

            severity = str(one.get("severity", "")).strip().lower()
            if severity not in ["high", "medium", "low"]:
                severity = "medium"

            reason = str(one.get("reason", "")).strip()
            suggestion = str(one.get("suggestion", "")).strip()
            if not reason and not suggestion:
                continue

            audit_results.append(
                {
                    "chunk_id": chunk_id,
                    "chunk_hash": chunk_hash,
                    "element_refs": element_refs,
                    "element_meta": element_meta,
                    "matched_rule_code": f"template-{idx:04d}",
                    "matched_rule_name": f"Template Check {idx:04d}",
                    "rule_level": "medium",
                    "severity": severity,
                    "quote": quote,
                    "reason": reason,
                    "suggestion": suggestion,
                }
            )

        result = {
            "audit_results": audit_results,
            "total_pairs": 1,
            "total_hits": len(audit_results),
            "output_language": output_language,
        }
        out_text = json.dumps(result, ensure_ascii=False)
        for m in dual_messages(self, out_text, result):
            yield m
