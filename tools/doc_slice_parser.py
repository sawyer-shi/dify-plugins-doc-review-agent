from collections.abc import Generator
from typing import Any, Dict, List
import json
import os
import hashlib
import re

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage

from tools.utils import clean_paths, save_upload_to_temp, strip_model_thoughts, invoke_llm, dual_messages
from docx import Document


def _normalize_strategy(slice_strategy: str, parse_hint_legacy: str) -> str:
    direct = (slice_strategy or "").strip().lower()
    allowed = {"default", "by_heading", "by_article", "by_paragraph", "by_sentence", "hybrid"}
    if direct in allowed:
        return direct

    hint = (parse_hint_legacy or "").strip().lower()
    if hint in allowed:
        return hint
    if "by_heading" in hint:
        return "by_heading"
    if "by_article" in hint:
        return "by_article"
    if "by_paragraph" in hint:
        return "by_paragraph"
    if "by_sentence" in hint:
        return "by_sentence"
    if "hybrid" in hint:
        return "hybrid"
    return "default"


def _is_heading_line(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if len(t) > 80:
        return False
    patterns = [
        r"^第[一二三四五六七八九十百千万0-9]+[章节部分篇]\b",
        r"^[一二三四五六七八九十]+[、.．)]",
        r"^\d+(?:\.\d+){0,3}[、.．)]",
        r"^(chapter|section)\s+\d+",
    ]
    return any(re.match(p, t, flags=re.IGNORECASE) for p in patterns)


def _is_article_line(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    patterns = [
        r"^第[一二三四五六七八九十百千万0-9]+条",
        r"^article\s+\d+",
        r"^clause\s+\d+",
        r"^\d+\.\d+(?:\.\d+)*",
    ]
    return any(re.match(p, t, flags=re.IGNORECASE) for p in patterns)


def _build_chunks(paragraphs: List[Dict[str, Any]], max_chunk_chars: int, strategy: str) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    current_texts: List[str] = []
    current_refs: List[str] = []
    current_para_hashes: List[Dict[str, Any]] = []
    current_len = 0
    chunk_id = 0

    def flush_current() -> None:
        nonlocal chunk_id, current_texts, current_refs, current_para_hashes, current_len
        if not current_texts:
            return
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

    for item in paragraphs:
        text = item["text"]
        if not text:
            continue
        ref = f"p:{item['para_id']}"

        if strategy == "by_paragraph":
            if len(text) <= max_chunk_chars:
                chunks.append({
                    "chunk_id": chunk_id,
                    "title": "",
                    "text": text,
                    "element_refs": [ref],
                    "element_meta": [{"ref": ref, "para_hash": item["para_hash"]}],
                    "chunk_hash": hashlib.sha1(text.encode("utf-8")).hexdigest()[:16],
                })
                chunk_id += 1
            else:
                start = 0
                while start < len(text):
                    part = text[start:start + max_chunk_chars]
                    chunks.append({
                        "chunk_id": chunk_id,
                        "title": "",
                        "text": part,
                        "element_refs": [ref],
                        "element_meta": [{"ref": ref, "para_hash": item["para_hash"]}],
                        "chunk_hash": hashlib.sha1(part.encode("utf-8")).hexdigest()[:16],
                    })
                    chunk_id += 1
                    start += max_chunk_chars
            continue

        boundary = False
        if strategy == "by_heading":
            boundary = _is_heading_line(text)
        elif strategy == "by_article":
            boundary = _is_article_line(text)
        elif strategy == "hybrid":
            boundary = _is_heading_line(text) or _is_article_line(text)

        if boundary and current_texts:
            flush_current()

        if current_len + len(text) + 1 > max_chunk_chars and current_texts:
            flush_current()

        current_texts.append(text)
        current_refs.append(ref)
        current_para_hashes.append({"ref": ref, "para_hash": item["para_hash"]})
        current_len += len(text) + 1

    flush_current()
    return chunks


def _split_sentences(text: str) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    parts = re.split(r"(?<=[。！？!?；;\.])\s+|(?<=[。！？!?；;\.])", t)
    out = [p.strip() for p in parts if p and p.strip()]
    return out if out else [t]


def _build_sentence_chunks(paragraphs: List[Dict[str, Any]], max_chunk_chars: int) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    chunk_id = 0
    current_texts: List[str] = []
    current_refs: List[str] = []
    current_meta: List[Dict[str, Any]] = []
    current_len = 0

    def flush() -> None:
        nonlocal chunk_id, current_texts, current_refs, current_meta, current_len
        if not current_texts:
            return
        chunk_text = "".join(current_texts).strip()
        chunks.append({
            "chunk_id": chunk_id,
            "title": "",
            "text": chunk_text,
            "element_refs": current_refs,
            "element_meta": current_meta,
            "chunk_hash": hashlib.sha1(chunk_text.encode("utf-8")).hexdigest()[:16],
        })
        chunk_id += 1
        current_texts = []
        current_refs = []
        current_meta = []
        current_len = 0

    for item in paragraphs:
        text = item["text"]
        if not text:
            continue
        ref = f"p:{item['para_id']}"
        sents = _split_sentences(text)
        for s in sents:
            add_len = len(s) + (1 if current_texts else 0)
            if current_len + add_len > max_chunk_chars and current_texts:
                flush()
            if current_texts:
                current_texts.append(" ")
            current_texts.append(s)
            current_len += add_len
            if ref not in current_refs:
                current_refs.append(ref)
                current_meta.append({"ref": ref, "para_hash": item["para_hash"]})

    flush()
    return chunks


class DocSliceParserTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        file_obj = tool_parameters.get("upload_file")
        parse_hint_legacy = str(tool_parameters.get("parse_hint") or "")
        slice_strategy = str(tool_parameters.get("slice_strategy") or "")
        max_chunk_chars = tool_parameters.get("max_chunk_chars", 1200)
        strategy = _normalize_strategy(slice_strategy, parse_hint_legacy)

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

            chunk_limit = int(max_chunk_chars or 1200)
            if chunk_limit <= 0:
                chunk_limit = 1200

            if strategy == "by_sentence":
                chunks = _build_sentence_chunks(paragraphs, chunk_limit)
            else:
                chunks = _build_chunks(paragraphs, chunk_limit, strategy)

            preview_blocks = []
            for chunk in chunks:
                preview = chunk["text"][:400].replace("\n", " ")
                preview_blocks.append({"chunk_id": chunk["chunk_id"], "preview": preview})

            system_prompt = f"""
You are a document parser assistant.

Parse hint:
{parse_hint_legacy}

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

            output = {
                "summary": summary_text,
                "chunks": chunks,
                "slice_strategy": strategy,
            }
            out_text = json.dumps(output, ensure_ascii=False)
            for m in dual_messages(self, out_text, output):
                yield m

        finally:
            clean_paths([temp_path] if temp_path else [])
