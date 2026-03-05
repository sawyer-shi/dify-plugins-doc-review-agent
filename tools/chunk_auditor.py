from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage

from tools.utils import strip_model_thoughts, invoke_llm, dual_messages, safe_json_load


class ChunkAuditorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        chunk_text = tool_parameters.get("chunk_text") or ""
        chunk_id = tool_parameters.get("chunk_id")
        rules = tool_parameters.get("rules") or ""
        extra_hint = tool_parameters.get("extra_hint") or ""

        if not isinstance(llm_model, dict):
            for m in dual_messages(self, "Error: model_config invalid.", {"error": "model_config invalid"}):
                yield m
            return

        system_prompt = f"""
You are a senior legal reviewer.

Rules input (may be plain checklist, or JSON from rule_loader):
{rules}

Chunk ID: {chunk_id}
Extra hint: {extra_hint}

Text to review:
{chunk_text}

Task:
Audit the text by the given rules, and prioritize strict matching to rule_code.
Return JSON only with the following structure:
{{
  "chunk_id": {chunk_id},
  "risks": [
    {{
      "matched_rule_code": "R001",
      "matched_rule_name": "...",
      "rule_level": "high|medium|low",
      "severity": "high|medium|low",
      "quote": "exact clause snippet",
      "reason": "why risky",
      "suggestion": "how to fix"
    }}
  ]
}}

Requirements:
1) If rule_code exists in rules input, always fill matched_rule_code.
2) quote must be an exact excerpt from chunk_text.
3) If no risk, return an empty risks array.
4) Output JSON only.
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
