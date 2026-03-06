from collections.abc import Generator
from typing import Any, Dict, List
import json
import os
import hashlib

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage

from tools.utils import clean_paths, save_upload_to_temp, strip_model_thoughts, invoke_llm, dual_messages
from docx import Document


class DocSliceParserTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        file_obj = tool_parameters.get("upload_file")
        parse_hint = tool_parameters.get("parse_hint") or ""
        max_chunk_chars = tool_parameters.get("max_chunk_chars", 1200)

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

            doc = Document(temp_path)
            paragraphs = []
            for idx, p in enumerate(doc.paragraphs):
                text = (p.text or "").strip()
                para_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12] if text else ""
                paragraphs.append({"para_id": idx, "text": text, "para_hash": para_hash})

            chunks: List[Dict[str, Any]] = []
            current_texts: List[str] = []
            current_refs: List[str] = []
            current_para_hashes: List[Dict[str, Any]] = []
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
                        "element_meta": current_para_hashes,
                        "chunk_hash": hashlib.sha1(chunk_text.encode("utf-8")).hexdigest()[:16],
                    })
                    chunk_id += 1
                    current_texts = []
                    current_refs = []
                    current_para_hashes = []
                    current_len = 0

                current_texts.append(text)
                current_refs.append(ref)
                current_para_hashes.append({"ref": ref, "para_hash": item["para_hash"]})
                current_len += len(text) + 1

            if current_texts:
                chunk_text = "\n".join(current_texts)
                chunks.append({
                    "chunk_id": chunk_id,
                    "title": "",
                    "text": chunk_text,
                    "element_refs": current_refs,
                    "element_meta": current_para_hashes,
                    "chunk_hash": hashlib.sha1(chunk_text.encode("utf-8")).hexdigest()[:16],
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
                for m in dual_messages(self, f"LLM Error: {str(e)}", {"error": f"LLM Error: {str(e)}"}):
                    yield m
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
                for m in dual_messages(self, "Error: Invalid JSON from parser model.", {"error": "Invalid JSON from parser model"}):
                    yield m
                return

            for chunk in chunks:
                title = titles_map.get(chunk["chunk_id"], "")
                chunk["title"] = title

            output = {"summary": summary_text, "chunks": chunks}
            out_text = json.dumps(output, ensure_ascii=False)
            for m in dual_messages(self, out_text, output):
                yield m

        finally:
            clean_paths([temp_path] if temp_path else [])
