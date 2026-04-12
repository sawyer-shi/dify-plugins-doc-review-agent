from collections.abc import Generator
import hashlib
import logging
from types import SimpleNamespace
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.entities.tool import ToolInvokeMessage
from docx import Document

from tools.utils import clean_paths, detect_text_language, invoke_llm, safe_json_load, save_upload_to_temp, strip_model_thoughts


logger = logging.getLogger(__name__)
WORD_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocAuditTool(Tool):
    @staticmethod
    def _get_subtool_class(operator: str) -> type[Tool]:
        if operator == "rule_loader":
            from tools.rule_loader import RuleLoaderTool

            return RuleLoaderTool
        if operator == "risk_aggregator":
            from tools.risk_aggregator import RiskAggregatorTool

            return RiskAggregatorTool
        if operator == "doc_annotator":
            from tools.doc_annotator import DocAnnotatorTool

            return DocAnnotatorTool
        if operator == "file_revision":
            from tools.file_revision import FileRevisionTool

            return FileRevisionTool
        raise ValueError(f"Unsupported subtool operator: {operator}")

    @staticmethod
    def _blob_to_file(blob_entry: dict[str, Any], fallback_name: str) -> Any:
        meta = blob_entry.get("meta") or {}
        filename = str(meta.get("filename") or meta.get("save_as") or fallback_name)
        return SimpleNamespace(blob=blob_entry.get("blob", b""), filename=filename, name=filename, original_filename=filename)

    @staticmethod
    def _normalize_audit_strategy(audit_strategy: str) -> str:
        value = str(audit_strategy or "balanced").strip().lower()
        allowed = {"balanced", "strict_precision", "high_recall", "severity_first", "compliance_explain"}
        return value if value in allowed else "balanced"

    @staticmethod
    def _strategy_instruction(strategy: str) -> str:
        mapping = {
            "balanced": "Balance precision and recall. Report only clear risks with concrete evidence.",
            "strict_precision": "Use strict precision. Only report when evidence is explicit and confidence is high.",
            "high_recall": "Use high recall. Report potential risks when there is plausible evidence, then explain uncertainty.",
            "severity_first": "Prioritize severe risks. Focus on high/medium severity first and be conservative on low severity findings.",
            "compliance_explain": "Write compliance-oriented reasoning. Explain the rule-fit logic and actionable remediation clearly.",
        }
        return mapping.get(strategy, mapping["balanced"])

    def _emit_error(self, step_index: int | None, step_name: str | None, detail: str) -> list[ToolInvokeMessage]:
        payload: dict[str, Any]
        if step_name:
            text = f"❌ {step_name}失败: {detail}"
            payload = {"error": f"{step_name}失败", "detail": detail, "step": step_name}
            if step_index is not None:
                payload["step_index"] = step_index
        else:
            text = f"❌ {detail}"
            payload = {"error": detail}
        logger.error(text)
        return [self.create_text_message(text), self.create_json_message(payload)]

    def _run_subtool(self, tool_cls: type[Tool], tool_parameters: dict[str, Any]) -> dict[str, Any]:
        last_text = ""
        last_json = None
        blobs: list[dict[str, Any]] = []
        tool = tool_cls(runtime=self.runtime, session=self.session)
        try:
            for message in tool._invoke(tool_parameters):
                if message.type == InvokeMessage.MessageType.TEXT and message.message is not None:
                    last_text = getattr(message.message, "text", "") or last_text
                elif message.type == InvokeMessage.MessageType.JSON and message.message is not None:
                    last_json = getattr(message.message, "json_object", None)
                elif message.type == InvokeMessage.MessageType.BLOB and message.message is not None:
                    blobs.append({"blob": getattr(message.message, "blob", b""), "meta": message.meta or {}})
        except Exception as e:
            return {"error": str(e)}

        if isinstance(last_json, dict) and last_json.get("error"):
            return {"error": str(last_json.get("error"))}
        if last_json is None and not blobs:
            return {"error": last_text or "No structured output returned"}
        return {"payload": last_json, "blobs": blobs}

    def _build_full_document_payload(self, upload_file: Any) -> dict[str, Any]:
        temp_path = None
        try:
            temp_path, _, ext = save_upload_to_temp(upload_file)
            if ext != ".docx":
                return {"error": "Only .docx is supported"}
            doc = Document(temp_path)

            paragraphs: list[dict[str, Any]] = []
            for idx, para in enumerate(doc.paragraphs):
                text = (para.text or "").strip()
                if not text:
                    continue
                para_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
                paragraphs.append({"para_id": idx, "text": text, "para_hash": para_hash})

            full_text = "\n".join([p["text"] for p in paragraphs]).strip()
            if not full_text:
                return {"summary": "", "chunks": []}

            element_refs = [f"p:{p['para_id']}" for p in paragraphs]
            element_meta = [{"ref": f"p:{p['para_id']}", "para_hash": p["para_hash"]} for p in paragraphs]
            full_chunk = {
                "chunk_id": 0,
                "title": "全文",
                "text": full_text,
                "element_refs": element_refs,
                "element_meta": element_meta,
                "chunk_hash": hashlib.sha1(full_text.encode("utf-8")).hexdigest()[:16],
            }
            return {"summary": "simple full-document audit", "chunks": [full_chunk], "audit_strategy": "single_pass"}
        except Exception as e:
            return {"error": str(e)}
        finally:
            clean_paths([temp_path] if temp_path else [])

    def _run_single_loop_audit(
        self,
        llm_model: dict[str, Any],
        slices_payload: dict[str, Any],
        rules_payload: dict[str, Any],
        extra_hint: str,
        output_language: str,
        audit_strategy: str,
    ) -> dict[str, Any]:
        chunks = slices_payload.get("chunks", []) if isinstance(slices_payload, dict) else []
        rules = rules_payload.get("rules", []) if isinstance(rules_payload, dict) else []
        if not chunks or not rules:
            return {"audit_results": [], "total_pairs": 0, "total_hits": 0, "audit_strategy": audit_strategy}

        full_chunk = chunks[0]
        doc_text = str(full_chunk.get("text", ""))
        if not doc_text.strip():
            return {"audit_results": [], "total_pairs": 0, "total_hits": 0, "audit_strategy": audit_strategy}

        if output_language == "auto":
            output_language = detect_text_language(doc_text)
        if output_language not in ["zh", "en", "ja", "ko", "es", "fr", "de", "pt", "ru", "ar"]:
            output_language = "en"

        strategy = self._normalize_audit_strategy(audit_strategy)
        strategy_instruction = self._strategy_instruction(strategy)

        total_pairs = 0
        results: list[dict[str, Any]] = []

        for rule in rules:
            rule_code = str(rule.get("rule_code", "")).strip()
            rule_name = str(rule.get("rule_name", "")).strip()
            rule_level = str(rule.get("rule_level", "")).strip().lower()
            rule_prompt = str(rule.get("rule_prompt", "")).strip()
            if not rule_code or not rule_prompt:
                continue

            total_pairs += 1
            prompt = f"""
You are a senior legal reviewer for short documents.

Audit strategy: {strategy}
Strategy guidance: {strategy_instruction}
Extra hint: {extra_hint}

Rule:
- rule_code: {rule_code}
- rule_name: {rule_name}
- rule_level: {rule_level}
- rule_prompt: {rule_prompt}

Document (full text):
{doc_text}

Task:
Judge whether the full document violates the single rule above.
Return JSON only:
{{
  "hit": true|false,
  "severity": "high|medium|low",
  "quote": "exact clause snippet",
  "reason": "why risky",
  "suggestion": "how to fix"
}}

Requirements:
1) quote must be exact text from the document when hit=true.
2) quote must be a single-line span (no newline) and length 20-120 characters.
3) if hit=false, keep quote/reason/suggestion empty string.
4) reason and suggestion language must be {output_language}.
5) output JSON only.
"""
            messages = [UserPromptMessage(content=prompt)]
            try:
                model_output = invoke_llm(self, llm_model, messages)
            except Exception as e:
                return {"error": f"LLM Error: {str(e)}"}

            one = safe_json_load(strip_model_thoughts(model_output), {})
            if not isinstance(one, dict):
                return {"error": "Invalid JSON from auditor model"}
            if not bool(one.get("hit")):
                continue

            quote = str(one.get("quote", "")).strip()
            if quote and quote not in doc_text:
                continue
            if "\n" in quote or "\r" in quote:
                continue
            if len(quote) < 20 or len(quote) > 120:
                continue

            severity = str(one.get("severity", "")).strip().lower()
            if severity not in ["high", "medium", "low"]:
                severity = rule_level if rule_level in ["high", "medium", "low"] else "medium"

            results.append(
                {
                    "chunk_id": full_chunk.get("chunk_id", 0),
                    "chunk_hash": str(full_chunk.get("chunk_hash", "")),
                    "element_refs": full_chunk.get("element_refs", []),
                    "element_meta": full_chunk.get("element_meta", []),
                    "matched_rule_code": rule_code,
                    "matched_rule_name": rule_name,
                    "rule_level": rule_level if rule_level in ["high", "medium", "low"] else "medium",
                    "severity": severity,
                    "quote": quote,
                    "reason": str(one.get("reason", "")).strip(),
                    "suggestion": str(one.get("suggestion", "")).strip(),
                }
            )

        return {
            "audit_results": results,
            "total_pairs": total_pairs,
            "total_hits": len(results),
            "output_language": output_language,
            "audit_strategy": strategy,
        }

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        upload_file = tool_parameters.get("upload_file")
        rules_file = tool_parameters.get("rules_file")
        audit_strategy = self._normalize_audit_strategy(tool_parameters.get("audit_strategy") or "balanced")
        extra_hint = tool_parameters.get("extra_hint") or ""
        output_language = tool_parameters.get("output_language") or "auto"
        merge_policy = tool_parameters.get("merge_policy") or "dedupe_by_rule_code_quote_location"
        annotation_style = tool_parameters.get("annotation_style") or "comment"
        output_file_name = str(tool_parameters.get("output_file_name") or "").strip()
        merge_strategy = tool_parameters.get("merge_strategy") or "keep_highest_risk"
        apply_to_original = tool_parameters.get("apply_to_original") or "no"
        output_json_mode = str(tool_parameters.get("output_json_mode") or "summary_only").strip().lower()
        output_file_mode = str(tool_parameters.get("output_file_mode") or "revised_only").strip().lower()

        if not upload_file:
            yield self.create_text_message("❌ 请输入待审核文档文件 upload_file")
            yield self.create_json_message({"error": "No file uploaded", "field": "upload_file"})
            return
        if not rules_file:
            yield self.create_text_message("❌ 请输入审核规则文件 rules_file")
            yield self.create_json_message({"error": "rules_file is required", "field": "rules_file"})
            return
        if not isinstance(llm_model, dict):
            yield self.create_text_message("❌ model_config invalid")
            yield self.create_json_message({"error": "model_config invalid", "field": "model_config"})
            return
        if output_json_mode not in {"summary_only", "detailed"}:
            output_json_mode = "summary_only"
        if output_file_mode not in {"revised_only", "both"}:
            output_file_mode = "revised_only"

        annotate_output_name = f"reviewed_{output_file_name}" if output_file_name else None
        revise_output_name = f"revised_reviewed_{output_file_name}" if output_file_name else None

        steps = [(1, "加载文档"), (2, "规则加载"), (3, "文档审核"), (4, "风险聚合"), (5, "文档标注"), (6, "文件修订")]
        yield self.create_text_message("🚀 文档审核启动中...")

        step_index = None
        step_name = None
        try:
            step_index, step_name = steps[0]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}")
            slices_payload = self._build_full_document_payload(upload_file)
            if slices_payload.get("error"):
                for m in self._emit_error(step_index, step_name, str(slices_payload.get("error"))):
                    yield m
                return
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成。")

            step_index, step_name = steps[1]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}")
            loader_result = self._run_subtool(self._get_subtool_class("rule_loader"), {"rules_file": rules_file})
            if loader_result.get("error"):
                for m in self._emit_error(step_index, step_name, str(loader_result.get("error"))):
                    yield m
                return
            rules_payload = loader_result.get("payload") or {}
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成。")

            step_index, step_name = steps[2]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}(处理时间会比较长，请耐心等待)")
            audit_payload = self._run_single_loop_audit(llm_model, slices_payload, rules_payload, extra_hint, output_language, audit_strategy)
            if audit_payload.get("error"):
                for m in self._emit_error(step_index, step_name, str(audit_payload.get("error"))):
                    yield m
                return
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成。")

            step_index, step_name = steps[3]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}")
            aggregate_result = self._run_subtool(
                self._get_subtool_class("risk_aggregator"),
                {"model_config": llm_model, "raw_results": audit_payload, "merge_policy": merge_policy},
            )
            if aggregate_result.get("error"):
                for m in self._emit_error(step_index, step_name, str(aggregate_result.get("error"))):
                    yield m
                return
            aggregate_payload = aggregate_result.get("payload") or {}
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成。")

            step_index, step_name = steps[4]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}(处理时间会比较长，请耐心等待)")
            annotate_result = self._run_subtool(
                self._get_subtool_class("doc_annotator"),
                {
                    "model_config": llm_model,
                    "upload_file": upload_file,
                    "audit_report": aggregate_payload,
                    "annotation_style": annotation_style,
                    "output_file_name": annotate_output_name,
                },
            )
            if annotate_result.get("error"):
                for m in self._emit_error(step_index, step_name, str(annotate_result.get("error"))):
                    yield m
                return
            annotate_payload = annotate_result.get("payload") or {}
            annotate_blobs = annotate_result.get("blobs") or []
            if not annotate_blobs:
                for m in self._emit_error(step_index, step_name, "标注文档未生成"):
                    yield m
                return
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成。")

            step_index, step_name = steps[5]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}")
            revision_input_file = self._blob_to_file(annotate_blobs[0], "reviewed.docx")
            revision_result = self._run_subtool(
                self._get_subtool_class("file_revision"),
                {
                    "model_config": llm_model,
                    "upload_file": revision_input_file,
                    "merge_strategy": merge_strategy,
                    "apply_to_original": apply_to_original,
                    "output_file_name": revise_output_name,
                },
            )
            if revision_result.get("error"):
                for m in self._emit_error(step_index, step_name, str(revision_result.get("error"))):
                    yield m
                return
            revision_payload = revision_result.get("payload") or {}
            revision_blobs = revision_result.get("blobs") or []
            if not revision_blobs:
                for m in self._emit_error(step_index, step_name, "修订文档未生成"):
                    yield m
                return
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成。")

            summary = {
                "annotation_count": int(annotate_payload.get("annotation_count", 0)) if isinstance(annotate_payload, dict) else 0,
                "chunk_count": len(slices_payload.get("chunks", [])) if isinstance(slices_payload, dict) else 0,
                "final_comment_count": int(revision_payload.get("final_comment_count", 0)) if isinstance(revision_payload, dict) else 0,
                "modified_count": int(revision_payload.get("modified_count", 0)) if isinstance(revision_payload, dict) else 0,
                "rule_count": int(rules_payload.get("rule_count", 0)) if isinstance(rules_payload, dict) and str(rules_payload.get("rule_count", "")).isdigit() else 0,
                "total_hits": int(aggregate_payload.get("summary", {}).get("output_hits", 0)) if isinstance(aggregate_payload, dict) and isinstance(aggregate_payload.get("summary"), dict) else int(audit_payload.get("total_hits", 0)),
                "total_pairs": int(audit_payload.get("total_pairs", 0)) if isinstance(audit_payload, dict) else 0,
            }
            detailed_payload = {
                "status": "ok",
                "slices": slices_payload,
                "rules": rules_payload,
                "audit": audit_payload,
                "aggregated_risks": aggregate_payload,
                "reviewed_file": annotate_payload,
                "revised_reviewed_file": revision_payload,
                "summary": summary,
            }
            yield self.create_text_message("🎯 文档审核完成！")
            if output_json_mode == "detailed":
                yield self.create_json_message(detailed_payload)
            else:
                yield self.create_json_message({"summary": summary})

            if output_file_mode == "both":
                for blob_entry in annotate_blobs:
                    yield self.create_blob_message(blob=blob_entry.get("blob", b""), meta=blob_entry.get("meta") or {"mime_type": WORD_MIME_TYPE})
            for blob_entry in revision_blobs:
                yield self.create_blob_message(blob=blob_entry.get("blob", b""), meta=blob_entry.get("meta") or {"mime_type": WORD_MIME_TYPE})
        except Exception as e:
            detail = str(e)
            logger.exception("Doc audit failed: %s", detail)
            for m in self._emit_error(step_index, step_name, detail):
                yield m
