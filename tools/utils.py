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


def dual_messages(tool: Any, text: str, payload: Any | None = None) -> List[Any]:
    out_text = "" if text is None else str(text)
    if payload is None:
        parsed = safe_json_load(out_text, None)
        payload = parsed if parsed is not None else {"text": out_text}
    return [
        tool.create_text_message(out_text),
        tool.create_json_message(payload),
    ]


def detect_text_language(text: str) -> str:
    if not text:
        return "en"

    sample = text[:5000]
    zh = len(re.findall(r"[\u4e00-\u9fff]", sample))
    ja = len(re.findall(r"[\u3040-\u30ff]", sample))
    ko = len(re.findall(r"[\uac00-\ud7af]", sample))
    ar = len(re.findall(r"[\u0600-\u06ff]", sample))
    latin = len(re.findall(r"[A-Za-z]", sample))

    max_count = max(zh, ja, ko, ar, latin)
    if max_count == zh and zh > 0:
        return "zh"
    if max_count == ja and ja > 0:
        return "ja"
    if max_count == ko and ko > 0:
        return "ko"
    if max_count == ar and ar > 0:
        return "ar"
    return "en"


def select_log_language(tool_parameters: dict[str, Any] | None = None) -> str:
    params = tool_parameters or {}
    output_language = str(params.get("output_language") or "").strip().lower()
    if output_language in {"zh", "zh_hans", "zh-hans", "zh_cn", "zh-cn", "chinese"}:
        return "zh"
    return "en"


def _msg(lang: str, zh: str, en: str) -> str:
    return zh if lang == "zh" else en


_MSGS = {
    "doc_audit": {
        "start": {"zh": "🚀 文档审核启动中...", "en": "🚀 Document audit starting..."},
        "running": {"zh": "{n}/{total} 正在执行：{step}", "en": "{n}/{total} Running: {step}"},
        "done": {"zh": "✅ {n}/{total} {step}完成。", "en": "✅ {n}/{total} {step} complete."},
        "done_long": {"zh": "{n}/{total} 正在执行：{step}(处理时间会比较长，请耐心等待)", "en": "{n}/{total} Running: {step} (this may take a while)"},
        "complete": {"zh": "🎯 文档审核完成！", "en": "🎯 Document audit complete!"},
        "err_no_file": {"zh": "❌ 请输入待审核文档文件 upload_file", "en": "❌ Please upload a document file (upload_file)"},
        "err_no_rules": {"zh": "❌ 请输入审核规则文件 rules_file", "en": "❌ Please upload a rules file (rules_file)"},
        "err_model_config": {"zh": "❌ model_config无效", "en": "❌ model_config invalid"},
        "err_step": {"zh": "❌ {step}失败: {detail}", "en": "❌ {step} failed: {detail}"},
        "err_general": {"zh": "❌ 文档审核执行异常: {detail}", "en": "❌ Document audit execution error: {detail}"},
    },
    "doc_slice_audit": {
        "start": {"zh": "🚀 文档切片审核启动中...", "en": "🚀 Document slice audit starting..."},
        "running": {"zh": "{n}/{total} 正在执行：{step}", "en": "{n}/{total} Running: {step}"},
        "done": {"zh": "✅ {n}/{total} {step}完成。", "en": "✅ {n}/{total} {step} complete."},
        "done_long": {"zh": "{n}/{total} 正在执行：{step}(处理时间会比较长，请耐心等待)", "en": "{n}/{total} Running: {step} (this may take a while)"},
        "complete": {"zh": "🎯 文档切片审核完成！", "en": "🎯 Document slice audit complete!"},
        "err_no_file": {"zh": "❌ 请输入待审核文档文件 upload_file", "en": "❌ Please upload a document file (upload_file)"},
        "err_no_rules": {"zh": "❌ 请输入审核规则文件 rules_file", "en": "❌ Please upload a rules file (rules_file)"},
        "err_model_config": {"zh": "❌ model_config无效", "en": "❌ model_config invalid"},
        "err_step": {"zh": "❌ {step}失败: {detail}", "en": "❌ {step} failed: {detail}"},
        "err_general": {"zh": "❌ 文档切片审核执行异常: {detail}", "en": "❌ Document slice audit execution error: {detail}"},
    },
    "doc_audit_template": {
        "start": {"zh": "🚀 文档范本审核启动中...", "en": "🚀 Template document audit starting..."},
        "running": {"zh": "{n}/{total} 正在执行：{step}", "en": "{n}/{total} Running: {step}"},
        "done": {"zh": "✅ {n}/{total} {step}完成。", "en": "✅ {n}/{total} {step} complete."},
        "done_long": {"zh": "{n}/{total} 正在执行：{step}(处理时间会比较长，请耐心等待)", "en": "{n}/{total} Running: {step} (this may take a while)"},
        "complete": {"zh": "🎯 文档范本审核完成！", "en": "🎯 Template document audit complete!"},
        "skip_load": {"zh": "{n}/{total} 正在执行：{step}（未提供 rules_file，跳过）", "en": "{n}/{total} Running: {step} (rules_file not provided, skipped)"},
        "skip_done": {"zh": "✅ {n}/{total} {step}已跳过。", "en": "✅ {n}/{total} {step} skipped."},
        "err_no_file": {"zh": "❌ 请输入待审核文档文件 upload_file", "en": "❌ Please upload a document file (upload_file)"},
        "err_model_config": {"zh": "❌ model_config无效", "en": "❌ model_config invalid"},
        "err_step": {"zh": "❌ {step}失败: {detail}", "en": "❌ {step} failed: {detail}"},
        "err_general": {"zh": "❌ 文档范本审核执行异常: {detail}", "en": "❌ Template document audit execution error: {detail}"},
    },
    "doc_slice_audit_template": {
        "start": {"zh": "🚀 文档切片范本审核启动中...", "en": "🚀 Document slice template audit starting..."},
        "running": {"zh": "{n}/{total} 正在执行：{step}", "en": "{n}/{total} Running: {step}"},
        "done": {"zh": "✅ {n}/{total} {step}完成。", "en": "✅ {n}/{total} {step} complete."},
        "done_long": {"zh": "{n}/{total} 正在执行：{step}(处理时间会比较长，请耐心等待)", "en": "{n}/{total} Running: {step} (this may take a while)"},
        "complete": {"zh": "🎯 文档切片范本审核完成！", "en": "🎯 Document slice template audit complete!"},
        "skip_load": {"zh": "{n}/{total} 正在执行：{step}（未提供 rules_file，跳过）", "en": "{n}/{total} Running: {step} (rules_file not provided, skipped)"},
        "skip_done": {"zh": "✅ {n}/{total} {step}已跳过。", "en": "✅ {n}/{total} {step} skipped."},
        "err_no_file": {"zh": "❌ 请输入待审核文档文件 upload_file", "en": "❌ Please upload a document file (upload_file)"},
        "err_model_config": {"zh": "❌ model_config无效", "en": "❌ model_config invalid"},
        "err_step": {"zh": "❌ {step}失败: {detail}", "en": "❌ {step} failed: {detail}"},
        "err_general": {"zh": "❌ 文档切片范本审核执行异常: {detail}", "en": "❌ Document slice template audit execution error: {detail}"},
    },
}


def fmt(tool_key: str, msg_key: str, lang: str, **kwargs: Any) -> str:
    tmpl = _MSGS.get(tool_key, {}).get(msg_key, {})
    text = tmpl.get(lang, tmpl.get("en", "")) if isinstance(tmpl, dict) else str(tmpl)
    return text.format(**kwargs) if kwargs else text
