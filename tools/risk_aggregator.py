from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage

from tools.utils import strip_model_thoughts, invoke_llm


class RiskAggregatorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        raw_results = tool_parameters.get("raw_results") or ""
        merge_policy = tool_parameters.get("merge_policy") or "dedupe_by_quote"

        if not isinstance(llm_model, dict):
            yield self.create_text_message("Error: model_config invalid.")
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
      "severity": "high|medium|low",
      "quote": "...",
      "reason": "...",
      "suggestion": "..."
    }}
  ]
}}

Rules:
1) Remove duplicates.
2) If conflicts, keep higher severity and merge suggestions.
3) Output JSON only.
"""

        messages = [UserPromptMessage(content=system_prompt)]

        try:
            result = invoke_llm(self, llm_model, messages)
        except Exception as e:
            yield self.create_text_message(f"LLM Error: {str(e)}")
            return

        cleaned = strip_model_thoughts(result)
        yield self.create_text_message(cleaned)
