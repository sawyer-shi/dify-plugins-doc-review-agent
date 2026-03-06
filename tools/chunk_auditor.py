from collections.abc import Generator
from typing import Any
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage

from tools.utils import strip_model_thoughts, invoke_llm, dual_messages, safe_json_load, detect_text_language


class ChunkAuditorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        doc_slices_text = tool_parameters.get("doc_slices_text") or ""
        rules_text = tool_parameters.get("rules_text") or ""
        extra_hint = tool_parameters.get("extra_hint") or ""
        output_language = str(tool_parameters.get("output_language") or "auto").strip().lower()

        if not isinstance(llm_model, dict):
            for m in dual_messages(self, "Error: model_config invalid.", {"error": "model_config invalid"}):
                yield m
            return

        slices_payload = safe_json_load(doc_slices_text, None)
        rules_payload = safe_json_load(rules_text, None)
        if not isinstance(slices_payload, dict) or not isinstance(slices_payload.get("chunks"), list):
            for m in dual_messages(self, "Error: doc_slices_text must be JSON with chunks list.", {"error": "Invalid doc_slices_text"}):
                yield m
            return
        if not isinstance(rules_payload, dict) or not isinstance(rules_payload.get("rules"), list):
            for m in dual_messages(self, "Error: rules_text must be JSON with rules list.", {"error": "Invalid rules_text"}):
                yield m
            return

        chunks = slices_payload.get("chunks", [])
        rules = rules_payload.get("rules", [])
        if not chunks or not rules:
            payload = {"audit_results": [], "total_pairs": 0, "total_hits": 0}
            for m in dual_messages(self, json.dumps(payload, ensure_ascii=False), payload):
                yield m
            return

        if output_language == "auto":
            joined = "\n".join([str(c.get("text", "")) for c in chunks[:8]])
            output_language = detect_text_language(joined)
        if output_language not in ["zh", "en", "ja", "ko", "es", "fr", "de", "pt", "ru", "ar"]:
            output_language = "en"

        results: list[dict[str, Any]] = []
        total_pairs = 0

        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            chunk_text = str(chunk.get("text", ""))
            element_refs = chunk.get("element_refs", [])
            element_meta = chunk.get("element_meta", [])
            chunk_hash = str(chunk.get("chunk_hash", "")).strip()
            if not chunk_text.strip():
                continue

            for rule in rules:
                rule_code = str(rule.get("rule_code", "")).strip()
                rule_name = str(rule.get("rule_name", "")).strip()
                rule_level = str(rule.get("rule_level", "")).strip().lower()
                rule_prompt = str(rule.get("rule_prompt", "")).strip()
                if not rule_code or not rule_prompt:
                    continue

                total_pairs += 1
                system_prompt = f"""
You are a senior legal reviewer.

Extra hint: {extra_hint}

Rule:
- rule_code: {rule_code}
- rule_name: {rule_name}
- rule_level: {rule_level}
- rule_prompt: {rule_prompt}

Chunk:
- chunk_id: {chunk_id}
- text: {chunk_text}

Task:
Judge whether this chunk violates the single rule above.
Return JSON only:
{{
  "hit": true|false,
  "severity": "high|medium|low",
  "quote": "exact clause snippet",
  "reason": "why risky",
  "suggestion": "how to fix"
}}

Requirements:
1) quote must be exact text from chunk when hit=true.
2) quote must be a single-line span (no newline) and length 20-120 characters.
3) if hit=false, keep quote/reason/suggestion empty string.
4) reason and suggestion language must be {output_language}.
5) output JSON only.
"""
                messages = [UserPromptMessage(content=system_prompt)]

                try:
                    result = invoke_llm(self, llm_model, messages)
                except Exception as e:
                    for m in dual_messages(self, f"LLM Error: {str(e)}", {"error": f"LLM Error: {str(e)}"}):
                        yield m
                    return

                cleaned = strip_model_thoughts(result)
                one = safe_json_load(cleaned, {})
                if not isinstance(one, dict):
                    for m in dual_messages(self, "Error: Invalid JSON from auditor model.", {"error": "Invalid JSON from auditor model"}):
                        yield m
                    return
                if not bool(one.get("hit")):
                    continue

                quote = str(one.get("quote", "")).strip()
                if quote and quote not in chunk_text:
                    continue
                if "\n" in quote or "\r" in quote:
                    continue
                if len(quote) < 20 or len(quote) > 120:
                    continue

                severity = str(one.get("severity", "")).strip().lower()
                if severity not in ["high", "medium", "low"]:
                    severity = rule_level if rule_level in ["high", "medium", "low"] else "medium"

                results.append({
                    "chunk_id": chunk_id,
                    "chunk_hash": chunk_hash,
                    "element_refs": element_refs,
                    "element_meta": element_meta,
                    "matched_rule_code": rule_code,
                    "matched_rule_name": rule_name,
                    "rule_level": rule_level if rule_level in ["high", "medium", "low"] else "medium",
                    "severity": severity,
                    "quote": quote,
                    "reason": str(one.get("reason", "")).strip(),
                    "suggestion": str(one.get("suggestion", "")).strip(),
                })

        payload = {
            "audit_results": results,
            "total_pairs": total_pairs,
            "total_hits": len(results),
            "output_language": output_language,
        }
        out_text = json.dumps(payload, ensure_ascii=False)
        for m in dual_messages(self, out_text, payload):
            yield m
