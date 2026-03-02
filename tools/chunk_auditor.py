from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage

from tools.utils import strip_model_thoughts, invoke_llm


class ChunkAuditorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        chunk_text = tool_parameters.get("chunk_text") or ""
        chunk_id = tool_parameters.get("chunk_id")
        rules = tool_parameters.get("rules") or ""
        extra_hint = tool_parameters.get("extra_hint") or ""

        if not isinstance(llm_model, dict):
            yield self.create_text_message("Error: model_config invalid.")
            return

        system_prompt = f"""
You are a senior legal reviewer.

Rules:
{rules}

Chunk ID: {chunk_id}
Extra hint: {extra_hint}

Text to review:
{chunk_text}

Task:
Return JSON only with the following structure:
{{
  "chunk_id": {chunk_id},
  "risks": [
    {{
      "severity": "high|medium|low",
      "quote": "exact clause snippet",
      "reason": "why risky",
      "suggestion": "how to fix"
    }}
  ]
}}

Rules:
1) Only output JSON.
2) If no risk, return an empty risks array.
"""

        messages = [UserPromptMessage(content=system_prompt)]

        try:
            result = invoke_llm(self, llm_model, messages)
        except Exception as e:
            yield self.create_text_message(f"LLM Error: {str(e)}")
            return

        cleaned = strip_model_thoughts(result)
        yield self.create_text_message(cleaned)
