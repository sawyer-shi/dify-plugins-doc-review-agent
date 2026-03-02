from collections.abc import Generator
from typing import Any, Dict, List
import json
import os

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage

from tools.utils import clean_paths, save_upload_to_temp, strip_model_thoughts, invoke_llm
from docx import Document


class DocSliceParserTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        file_obj = tool_parameters.get("upload_file")
        parse_hint = tool_parameters.get("parse_hint") or ""
        max_chunk_chars = tool_parameters.get("max_chunk_chars", 1200)

        if not isinstance(llm_model, dict):
            yield self.create_text_message("Error: model_config invalid.")
            return
        if not file_obj:
            yield self.create_text_message("Error: No file uploaded.")
            return

        temp_path = None
        try:
            temp_path, original_name, ext = save_upload_to_temp(file_obj)

            if ext != ".docx":
                yield self.create_text_message("Error: Only .docx is supported.")
                return

            doc = Document(temp_path)
            paragraphs = []
            for idx, p in enumerate(doc.paragraphs):
                text = (p.text or "").strip()
                paragraphs.append({"para_id": idx, "text": text})

            chunks: List[Dict[str, Any]] = []
            current_texts: List[str] = []
            current_refs: List[str] = []
            current_len = 0
            chunk_id = 0

            for item in paragraphs:
                text = item["text"]
                if not text:
                    continue
                ref = f"p:{item['para_id']}"
                if current_len + len(text) + 1 > max_chunk_chars and current_texts:
                    chunk_text = "\n".join(current_texts)
                    chunks.append({
                        "chunk_id": chunk_id,
                        "title": "",
                        "text": chunk_text,
                        "element_refs": current_refs,
                    })
                    chunk_id += 1
                    current_texts = []
                    current_refs = []
                    current_len = 0

                current_texts.append(text)
                current_refs.append(ref)
                current_len += len(text) + 1

            if current_texts:
                chunks.append({
                    "chunk_id": chunk_id,
                    "title": "",
                    "text": "\n".join(current_texts),
                    "element_refs": current_refs,
                })

            preview_blocks = []
            for chunk in chunks:
                preview = chunk["text"][:400].replace("\n", " ")
                preview_blocks.append({"chunk_id": chunk["chunk_id"], "preview": preview})

            system_prompt = f"""
You are a document parser assistant.

Parse hint:
{parse_hint}

Chunk previews:
{json.dumps(preview_blocks, ensure_ascii=True)}

Task:
Return JSON only with structure:
{{
  "summary": "short document summary",
  "titles": [{{"chunk_id": 0, "title": "..."}}]
}}
"""

            messages = [UserPromptMessage(content=system_prompt)]

            try:
                result = invoke_llm(self, llm_model, messages)
            except Exception as e:
                yield self.create_text_message(f"LLM Error: {str(e)}")
                return

            cleaned = strip_model_thoughts(result)
            titles_map: Dict[int, str] = {}
            summary_text = ""
            try:
                parsed = json.loads(cleaned)
                summary_text = parsed.get("summary", "") or ""
                for item in parsed.get("titles", []):
                    if isinstance(item, dict) and "chunk_id" in item:
                        titles_map[int(item["chunk_id"])] = str(item.get("title", ""))
            except Exception:
                summary_text = ""

            for chunk in chunks:
                title = titles_map.get(chunk["chunk_id"], "")
                chunk["title"] = title

            output = {"summary": summary_text, "chunks": chunks}
            yield self.create_text_message(json.dumps(output, ensure_ascii=True))

        finally:
            clean_paths([temp_path] if temp_path else [])
