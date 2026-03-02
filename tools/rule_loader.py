from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage

from tools.utils import strip_model_thoughts, invoke_llm


class RuleLoaderTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        doc_summary = tool_parameters.get("doc_summary") or ""
        audit_level = tool_parameters.get("audit_level") or "strict"
        rule_hint = tool_parameters.get("rule_hint") or ""

        if not isinstance(llm_model, dict):
            yield self.create_text_message("Error: model_config invalid.")
            return

        system_prompt = f"""
You are a legal review rule retriever.

Document summary:
{doc_summary}

Audit level: {audit_level}
Rule hint: {rule_hint}

Task:
Return a ruleset in plain text. It should include:
- Document type guess
- Checklist of rules
- Severity guidance (high/medium/low)

Rules:
1) Output plain text only.
2) Keep it concise but actionable.
"""

        messages = [UserPromptMessage(content=system_prompt)]

        try:
            result = invoke_llm(self, llm_model, messages)
        except Exception as e:
            yield self.create_text_message(f"LLM Error: {str(e)}")
            return

        cleaned = strip_model_thoughts(result)
        yield self.create_text_message(cleaned)
