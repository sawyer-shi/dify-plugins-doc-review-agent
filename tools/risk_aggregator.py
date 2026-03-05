from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage

from tools.utils import strip_model_thoughts, invoke_llm, dual_messages, safe_json_load


class RiskAggregatorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        raw_results = tool_parameters.get("raw_results") or ""
        merge_policy = tool_parameters.get("merge_policy") or "dedupe_by_quote"

        if not isinstance(llm_model, dict):
            for m in dual_messages(self, "Error: model_config invalid.", {"error": "model_config invalid"}):
                yield m
            return

        system_prompt = f"""
You are a risk aggregator for document review.

Raw audit results (JSON or text):
{raw_results}

Merge policy: {merge_policy}

Task:
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
5) Output JSON only.
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
