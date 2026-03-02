import json
import os
import re
import tempfile
from typing import Any, Dict, List, Tuple

import shutil

from dify_plugin.entities.model.message import UserPromptMessage



def strip_model_thoughts(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL)
    text = re.sub(r"```(?:json)?", "", text)
    return text.strip()


def safe_json_load(text: str, default: Any) -> Any:
    try:
        cleaned = strip_model_thoughts(text)
        return json.loads(cleaned)
    except Exception:
        return default


def best_filename(file_obj: Any, default_name: str = "document") -> str:
    candidates = []
    for attr in ["original_filename", "upload_filename", "filename", "name"]:
        if hasattr(file_obj, attr):
            val = getattr(file_obj, attr)
            if isinstance(val, str) and val:
                candidates.append(val)
    for name in candidates:
        base = os.path.basename(name)
        if base:
            return base
    return default_name


def save_upload_to_temp(file_obj: Any) -> Tuple[str, str, str]:
    content = getattr(file_obj, "blob", None)
    if content is None:
        raise ValueError("upload_file missing blob")

    original = best_filename(file_obj)
    _, ext = os.path.splitext(original)
    ext = ext.lower() or ".bin"

    fd, temp_path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        f.write(content)

    return temp_path, original, ext


def save_bytes_to_temp(data: bytes, suffix: str) -> str:
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return temp_path


def clean_paths(paths: List[str]) -> None:
    for p in paths:
        if p and os.path.exists(p):
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
            except Exception:
                pass


def invoke_llm(tool: Any, llm_model: Dict[str, Any], messages: List[UserPromptMessage]) -> str:
    invoke_fn = getattr(tool, "invoke_model", None)
    if callable(invoke_fn):
        response = invoke_fn(model=llm_model, messages=messages)
        msg = getattr(response, "message", None)
        if msg is not None:
            return getattr(msg, "content", "")
        return getattr(response, "content", str(response))

    session = getattr(tool, "session", None)
    if session and getattr(session, "model", None):
        llm_service = getattr(session.model, "llm", None)
        if not llm_service:
            raise AttributeError("No 'llm' service found.")
        response = llm_service.invoke(model_config=llm_model, prompt_messages=messages, stream=False)
        if hasattr(response, "message"):
            return response.message.content
        return getattr(response, "content", str(response))

    raise AttributeError("No invoke interface found.")
