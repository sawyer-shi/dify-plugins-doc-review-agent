from collections.abc import Generator
from typing import Any
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage

from tools.utils import strip_model_thoughts, invoke_llm, dual_messages, safe_json_load


class RiskAggregatorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        raw_results = tool_parameters.get("raw_results") or ""
        merge_policy = tool_parameters.get("merge_policy") or "dedupe_by_rule_code_quote"

        if not isinstance(llm_model, dict):
            for m in dual_messages(self, "Error: model_config invalid.", {"error": "model_config invalid"}):
                yield m
            return

        raw_payload = safe_json_load(raw_results, None)
        if isinstance(raw_payload, dict) and isinstance(raw_payload.get("audit_results"), list):
            dedup: dict[tuple[str, str], dict[str, Any]] = {}
            severity_rank = {"low": 1, "medium": 2, "high": 3}
            for item in raw_payload.get("audit_results", []):
                if not isinstance(item, dict):
                    continue
                code = str(item.get("matched_rule_code", "")).strip() or "NO_RULE"
                quote = str(item.get("quote", "")).strip()
                if not quote:
                    quote = str(item.get("reason", "")).strip()[:80]
                key = (code, quote)

                incoming = dict(item)
                sev = str(incoming.get("severity", "")).strip().lower()
                if sev not in severity_rank:
                    sev = str(incoming.get("rule_level", "medium")).strip().lower()
                if sev not in severity_rank:
                    sev = "medium"
                incoming["severity"] = sev

                if key not in dedup:
                    dedup[key] = incoming
                    continue

                existing = dedup[key]
                ex_sev = str(existing.get("severity", "medium")).strip().lower()
                if severity_rank.get(sev, 2) > severity_rank.get(ex_sev, 2):
                    existing["severity"] = sev

                ex_sug = str(existing.get("suggestion", "")).strip()
                in_sug = str(incoming.get("suggestion", "")).strip()
                if in_sug and in_sug not in ex_sug:
                    existing["suggestion"] = f"{ex_sug} / {in_sug}" if ex_sug else in_sug

                if not existing.get("element_refs") and incoming.get("element_refs"):
                    existing["element_refs"] = incoming.get("element_refs")
                if not existing.get("chunk_id") and incoming.get("chunk_id") is not None:
                    existing["chunk_id"] = incoming.get("chunk_id")

            merged = list(dedup.values())
            payload = {
                "risks": merged,
                "summary": {
                    "input_hits": len(raw_payload.get("audit_results", [])),
                    "output_hits": len(merged),
                    "total_pairs": raw_payload.get("total_pairs", 0),
                },
                "merge_policy": merge_policy,
            }
            out_text = json.dumps(payload, ensure_ascii=False)
            for m in dual_messages(self, out_text, payload):
                yield m
            return

        system_prompt = f"""
You are a risk aggregator for document review.

Raw audit results (JSON or text):
{raw_results}

Merge policy: {merge_policy}

Task:
The input may come from chunk_auditor as:
{{
  "audit_results": [...],
  "total_pairs": number,
  "total_hits": number
}}

Return JSON only with structure:
{{
  "risks": [
    {{
      "chunk_id": 0,
      "matched_rule_code": "R001",
      "matched_rule_name": "...",
      "rule_level": "high|medium|low",
      "severity": "high|medium|low",
      "quote": "...",
      "reason": "...",
      "suggestion": "..."
    }}
  ]
}}

Rules:
1) Remove duplicates by key: matched_rule_code + quote.
2) If matched_rule_code is missing, fallback key: quote.
3) If conflicts, keep higher severity and merge suggestions.
4) Keep matched_rule_name and rule_level when available.
5) Preserve element_refs when present.
6) Output JSON only.
"""

        messages = [UserPromptMessage(content=system_prompt)]

        try:
            result = invoke_llm(self, llm_model, messages)
        except Exception as e:
            for m in dual_messages(self, f"LLM Error: {str(e)}", {"error": f"LLM Error: {str(e)}"}):
                yield m
            return

        cleaned = strip_model_thoughts(result)
        payload = safe_json_load(cleaned, {"text": cleaned})
        for m in dual_messages(self, cleaned, payload):
            yield m
