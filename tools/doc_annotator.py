from collections.abc import Generator
from typing import Any
import os
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage

from tools.utils import clean_paths, save_upload_to_temp, strip_model_thoughts, invoke_llm, dual_messages
from docx import Document


class DocAnnotatorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        file_obj = tool_parameters.get("upload_file")
        audit_report = tool_parameters.get("audit_report") or ""
        output_file_name = tool_parameters.get("output_file_name")
        annotation_style = tool_parameters.get("annotation_style") or "comment"

        if not isinstance(llm_model, dict):
            for m in dual_messages(self, "Error: model_config invalid.", {"error": "model_config invalid"}):
                yield m
            return
        if not file_obj:
            for m in dual_messages(self, "Error: No file uploaded.", {"error": "No file uploaded"}):
                yield m
            return

        temp_path = None
        try:
            temp_path, original_name, ext = save_upload_to_temp(file_obj)
            if ext != ".docx":
                for m in dual_messages(self, "Error: Only .docx is supported.", {"error": "Only .docx is supported"}):
                    yield m
                return

            if not output_file_name or not str(output_file_name).strip():
                base, _ = os.path.splitext(original_name)
                output_file_name = f"reviewed_{base}"

            system_prompt = f"""
You are a document annotation assistant.

Audit report (JSON or text):
{audit_report}

Annotation style: {annotation_style}

Task:
Return JSON only with structure:
{{
  "annotations": [
    {{
      "chunk_id": 0,
      "matched_rule_code": "R001",
      "severity": "high|medium|low",
      "comment": "short comment text"
    }}
  ]
}}

Comment style requirements:
1) Build comment in this style: [R001][high] ...
2) If matched_rule_code missing, use [NO_RULE].
3) Keep each comment concise and actionable.
"""

            messages = [UserPromptMessage(content=system_prompt)]

            try:
                result = invoke_llm(self, llm_model, messages)
            except Exception as e:
                for m in dual_messages(self, f"LLM Error: {str(e)}", {"error": f"LLM Error: {str(e)}"}):
                    yield m
                return

            annotation_json = strip_model_thoughts(result)
            annotations = []
            try:
                parsed = json.loads(annotation_json)
                annotations = parsed.get("annotations", [])
            except Exception:
                annotations = []

            doc = Document(temp_path)
            para_map = {idx: p for idx, p in enumerate(doc.paragraphs)}

            for item in annotations:
                try:
                    chunk_id = int(item.get("chunk_id"))
                except Exception:
                    continue
                comment_text = str(item.get("comment", "")).strip()
                if not comment_text:
                    continue

                code = str(item.get("matched_rule_code", "")).strip() or "NO_RULE"
                severity = str(item.get("severity", "")).strip().lower() or "medium"
                if severity not in ["high", "medium", "low"]:
                    severity = "medium"
                final_comment = f"[{code}][{severity}] {comment_text}"

                para = para_map.get(chunk_id)
                if para is None:
                    refs = item.get("element_refs", [])
                    if isinstance(refs, list) and refs:
                        first_ref = str(refs[0])
                        if first_ref.startswith("p:"):
                            try:
                                pid = int(first_ref.split(":", 1)[1])
                                para = para_map.get(pid)
                            except Exception:
                                para = None
                if not para:
                    continue
                runs = list(para.runs)
                if not runs:
                    run = para.add_run(para.text)
                    runs = [run]
                doc.add_comment(runs, final_comment, author="DocReview", initials="DR")

            output_path = os.path.join(os.path.dirname(temp_path), f"{output_file_name}{ext}")
            doc.save(output_path)
            with open(output_path, "rb") as f:
                data = f.read()

            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            file_name = f"{output_file_name}{ext}"
            summary_payload = {
                "status": "ok",
                "output_file": file_name,
                "annotation_count": len(annotations),
            }
            for m in dual_messages(self, json.dumps(summary_payload, ensure_ascii=False), summary_payload):
                yield m
            yield self.create_blob_message(blob=data, meta={"mime_type": mime_type, "save_as": file_name, "filename": file_name})

        finally:
            clean_paths([temp_path] if temp_path else [])
