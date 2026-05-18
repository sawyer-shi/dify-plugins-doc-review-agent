from collections.abc import Generator
import logging
from types import SimpleNamespace
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.utils import fmt, select_log_language


logger = logging.getLogger(__name__)
WORD_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocSliceAuditTemplateTool(Tool):
    @staticmethod
    def _get_subtool_class(operator: str) -> type[Tool]:
        if operator == "doc_slice_parser":
            from tools.doc_slice_parser import DocSliceParserTool

            return DocSliceParserTool
        if operator == "rule_loader":
            from tools.rule_loader import RuleLoaderTool

            return RuleLoaderTool
        if operator == "chunk_auditor":
            from tools.chunk_auditor import ChunkAuditorTool

            return ChunkAuditorTool
        if operator == "template_chunk_auditor":
            from tools.template_chunk_auditor import TemplateChunkAuditorTool

            return TemplateChunkAuditorTool
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
    def _error_detail(payload: Any, fallback_text: str = "") -> str:
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("error") or payload.get("message")
            if detail:
                return str(detail)
        if fallback_text:
            return str(fallback_text)
        return "Unknown error"

    @staticmethod
    def _blob_to_file(blob_entry: dict[str, Any], fallback_name: str) -> Any:
        meta = blob_entry.get("meta") or {}
        filename = str(meta.get("filename") or meta.get("save_as") or fallback_name)
        return SimpleNamespace(blob=blob_entry.get("blob", b""), filename=filename, name=filename, original_filename=filename)

    def _emit_error(self, step_index: int | None, step_name: str | None, detail: str) -> list[ToolInvokeMessage]:
        lang = getattr(self, "_lang", "en")
        payload: dict[str, Any]
        if step_name:
            text = fmt("doc_slice_audit_template", "err_step", lang, step=step_name, detail=detail)
            payload = {"error": f"{step_name} failed", "detail": detail, "step": step_name}
            if step_index is not None:
                payload["step_index"] = step_index
        else:
            text = fmt("doc_slice_audit_template", "err_general", lang, detail=detail)
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
            return {"error": self._error_detail(last_json, last_text)}
        if last_json is None and not blobs:
            return {"error": self._error_detail(last_json, last_text or "No structured output returned")}
        return {"payload": last_json, "blobs": blobs, "text": last_text}

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        label_lang = select_log_language(tool_parameters)
        self._lang = label_lang
        steps = [
            (1, "审核文档切片", "Audit document slices"),
            (2, "范本文档切片", "Template slices"),
            (3, "规则加载", "Load rules"),
            (4, "规则分片审核", "Rule chunk audit"),
            (5, "范本分片对比审核", "Template compare"),
            (6, "风险聚合", "Aggregate risks"),
            (7, "文档标注", "Annotate"),
            (8, "文件修订", "Revise"),
        ]
        llm_model = tool_parameters.get("model_config")
        upload_file = tool_parameters.get("upload_file")
        template_file = tool_parameters.get("template_file")
        rules_file = tool_parameters.get("rules_file")

        if not upload_file:
            yield self.create_text_message(fmt("doc_slice_audit_template", "err_no_file", label_lang))
            yield self.create_json_message({"error": "No file uploaded", "field": "upload_file"})
            return
        if not template_file:
            yield self.create_text_message(fmt("doc_slice_audit_template", "err_no_file", label_lang))
            yield self.create_json_message({"error": "template_file is required", "field": "template_file"})
            return
        if not isinstance(llm_model, dict):
            yield self.create_text_message(fmt("doc_slice_audit_template", "err_model_config", label_lang))
            yield self.create_json_message({"error": "model_config invalid", "field": "model_config"})
            return

        parse_hint = tool_parameters.get("parse_hint") or ""
        slice_strategy = tool_parameters.get("slice_strategy") or ""
        max_chunk_chars = tool_parameters.get("max_chunk_chars", 1200)
        extra_hint = tool_parameters.get("extra_hint") or ""
        output_language = tool_parameters.get("output_language") or "auto"
        thread_num = tool_parameters.get("thread_num", 1)
        merge_policy = tool_parameters.get("merge_policy") or "dedupe_by_rule_code_quote_location"
        annotation_style = tool_parameters.get("annotation_style") or "comment"
        output_file_name = str(tool_parameters.get("output_file_name") or "").strip()
        merge_strategy = tool_parameters.get("merge_strategy") or "keep_highest_risk"
        apply_to_original = tool_parameters.get("apply_to_original") or "no"
        output_json_mode = str(tool_parameters.get("output_json_mode") or "summary_only").strip().lower()
        output_file_mode = str(tool_parameters.get("output_file_mode") or "revised_only").strip().lower()

        if output_json_mode not in {"summary_only", "detailed"}:
            output_json_mode = "summary_only"
        if output_file_mode not in {"revised_only", "both"}:
            output_file_mode = "revised_only"

        annotate_output_name = f"annotated_{output_file_name}" if output_file_name else None
        revise_output_name = output_file_name or None

        yield self.create_text_message(fmt("doc_slice_audit_template", "start", label_lang))

        try:
            n, step_zh, step_en = steps[0]
            step = step_zh if label_lang == "zh" else step_en
            yield self.create_text_message(fmt("doc_slice_audit_template", "running", label_lang, n=n, total=8, step=step))
            doc_parse_result = self._run_subtool(
                self._get_subtool_class("doc_slice_parser"),
                {
                    "model_config": llm_model,
                    "upload_file": upload_file,
                    "parse_hint": parse_hint,
                    "slice_strategy": slice_strategy,
                    "max_chunk_chars": max_chunk_chars,
                },
            )
            if doc_parse_result.get("error"):
                for m in self._emit_error(1, "审核文档切片", str(doc_parse_result["error"])):
                    yield m
                return
            slices_payload = doc_parse_result.get("payload") or {}
            yield self.create_text_message(fmt("doc_slice_audit_template", "done", label_lang, n=n, total=8, step=step))

            n, step_zh, step_en = steps[1]
            step = step_zh if label_lang == "zh" else step_en
            yield self.create_text_message(fmt("doc_slice_audit_template", "running", label_lang, n=n, total=8, step=step))
            template_parse_result = self._run_subtool(
                self._get_subtool_class("doc_slice_parser"),
                {
                    "model_config": llm_model,
                    "upload_file": template_file,
                    "parse_hint": parse_hint,
                    "slice_strategy": slice_strategy,
                    "max_chunk_chars": max_chunk_chars,
                },
            )
            if template_parse_result.get("error"):
                for m in self._emit_error(2, "范本文档切片", str(template_parse_result["error"])):
                    yield m
                return
            template_slices_payload = template_parse_result.get("payload") or {}
            yield self.create_text_message(fmt("doc_slice_audit_template", "done", label_lang, n=n, total=8, step=step))

            n, step_zh, step_en = steps[2]
            step = step_zh if label_lang == "zh" else step_en
            rules_payload: dict[str, Any] = {"rules": [], "rule_count": 0}
            rule_audit_payload: dict[str, Any] = {"audit_results": [], "total_pairs": 0, "total_hits": 0}
            if rules_file:
                yield self.create_text_message(fmt("doc_slice_audit_template", "running", label_lang, n=n, total=8, step=step))
                loader_result = self._run_subtool(self._get_subtool_class("rule_loader"), {"rules_file": rules_file})
                if loader_result.get("error"):
                    for m in self._emit_error(3, "规则加载", str(loader_result["error"])):
                        yield m
                    return
                rules_payload = loader_result.get("payload") or {}
                yield self.create_text_message(fmt("doc_slice_audit_template", "done", label_lang, n=n, total=8, step=step))

                n, step_zh, step_en = steps[3]
                step = step_zh if label_lang == "zh" else step_en
                yield self.create_text_message(fmt("doc_slice_audit_template", "done_long", label_lang, n=n, total=8, step=step))
                audit_result = self._run_subtool(
                    self._get_subtool_class("chunk_auditor"),
                    {
                        "model_config": llm_model,
                        "doc_slices_text": slices_payload,
                        "rules_text": rules_payload,
                        "extra_hint": extra_hint,
                        "output_language": output_language,
                        "thread_num": thread_num,
                    },
                )
                if audit_result.get("error"):
                    for m in self._emit_error(4, "规则分片审核", str(audit_result["error"])):
                        yield m
                    return
                rule_audit_payload = audit_result.get("payload") or {}
                yield self.create_text_message(fmt("doc_slice_audit_template", "done", label_lang, n=n, total=8, step=step))
            else:
                yield self.create_text_message(fmt("doc_slice_audit_template", "skip_load", label_lang, n=n, total=8, step=step))
                yield self.create_text_message(fmt("doc_slice_audit_template", "skip_done", label_lang, n=n, total=8, step=step))

                n, step_zh, step_en = steps[3]
                step = step_zh if label_lang == "zh" else step_en
                yield self.create_text_message(fmt("doc_slice_audit_template", "skip_load", label_lang, n=n, total=8, step=step))
                yield self.create_text_message(fmt("doc_slice_audit_template", "skip_done", label_lang, n=n, total=8, step=step))

            n, step_zh, step_en = steps[4]
            step = step_zh if label_lang == "zh" else step_en
            yield self.create_text_message(fmt("doc_slice_audit_template", "done_long", label_lang, n=n, total=8, step=step))
            template_audit_result = self._run_subtool(
                self._get_subtool_class("template_chunk_auditor"),
                {
                    "model_config": llm_model,
                    "template_slices_text": template_slices_payload,
                    "doc_slices_text": slices_payload,
                    "extra_hint": extra_hint,
                    "output_language": output_language,
                },
            )
            if template_audit_result.get("error"):
                for m in self._emit_error(5, "范本分片对比审核", str(template_audit_result["error"])):
                    yield m
                return
            template_audit_payload = template_audit_result.get("payload") or {}
            yield self.create_text_message(fmt("doc_slice_audit_template", "done", label_lang, n=n, total=8, step=step))

            combined_raw = {
                "json": [rule_audit_payload, template_audit_payload],
                "total_pairs": int(rule_audit_payload.get("total_pairs", 0)) + int(template_audit_payload.get("total_pairs", 0)),
            }

            n, step_zh, step_en = steps[5]
            step = step_zh if label_lang == "zh" else step_en
            yield self.create_text_message(fmt("doc_slice_audit_template", "running", label_lang, n=n, total=8, step=step))
            aggregate_result = self._run_subtool(
                self._get_subtool_class("risk_aggregator"),
                {"model_config": llm_model, "raw_results": combined_raw, "merge_policy": merge_policy},
            )
            if aggregate_result.get("error"):
                for m in self._emit_error(6, "风险聚合", str(aggregate_result["error"])):
                    yield m
                return
            aggregate_payload = aggregate_result.get("payload") or {}
            yield self.create_text_message(fmt("doc_slice_audit_template", "done", label_lang, n=n, total=8, step=step))

            n, step_zh, step_en = steps[6]
            step = step_zh if label_lang == "zh" else step_en
            yield self.create_text_message(fmt("doc_slice_audit_template", "done_long", label_lang, n=n, total=8, step=step))
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
                for m in self._emit_error(7, "文档标注", str(annotate_result["error"])):
                    yield m
                return
            annotate_payload = annotate_result.get("payload") or {}
            annotate_blobs = annotate_result.get("blobs") or []
            if not annotate_blobs:
                for m in self._emit_error(7, "文档标注", "标注文档未生成"):
                    yield m
                return
            yield self.create_text_message(fmt("doc_slice_audit_template", "done", label_lang, n=n, total=8, step=step))

            n, step_zh, step_en = steps[7]
            step = step_zh if label_lang == "zh" else step_en
            yield self.create_text_message(fmt("doc_slice_audit_template", "running", label_lang, n=n, total=8, step=step))
            revision_result = self._run_subtool(
                self._get_subtool_class("file_revision"),
                {
                    "model_config": llm_model,
                    "upload_file": self._blob_to_file(annotate_blobs[0], "annotated.docx"),
                    "merge_strategy": merge_strategy,
                    "apply_to_original": apply_to_original,
                    "output_file_name": revise_output_name,
                },
            )
            if revision_result.get("error"):
                for m in self._emit_error(8, "文件修订", str(revision_result["error"])):
                    yield m
                return
            revision_payload = revision_result.get("payload") or {}
            revision_blobs = revision_result.get("blobs") or []
            if not revision_blobs:
                for m in self._emit_error(8, "文件修订", "修订文档未生成"):
                    yield m
                return
            yield self.create_text_message(fmt("doc_slice_audit_template", "done", label_lang, n=n, total=8, step=step))

            summary = {
                "annotation_count": int(annotate_payload.get("annotation_count", 0)) if isinstance(annotate_payload, dict) else 0,
                "chunk_count": len(slices_payload.get("chunks", [])) if isinstance(slices_payload, dict) else 0,
                "template_chunk_count": len(template_slices_payload.get("chunks", [])) if isinstance(template_slices_payload, dict) else 0,
                "rule_count": int(rules_payload.get("rule_count", 0)) if isinstance(rules_payload, dict) and str(rules_payload.get("rule_count", "")).isdigit() else 0,
                "rule_total_hits": int(rule_audit_payload.get("total_hits", 0)) if isinstance(rule_audit_payload, dict) else 0,
                "template_total_hits": int(template_audit_payload.get("total_hits", 0)) if isinstance(template_audit_payload, dict) else 0,
                "total_hits": int(aggregate_payload.get("summary", {}).get("output_hits", 0)) if isinstance(aggregate_payload, dict) and isinstance(aggregate_payload.get("summary"), dict) else 0,
                "total_pairs": combined_raw["total_pairs"],
                "final_comment_count": int(revision_payload.get("final_comment_count", 0)) if isinstance(revision_payload, dict) else 0,
                "modified_count": int(revision_payload.get("modified_count", 0)) if isinstance(revision_payload, dict) else 0,
            }

            detailed_payload = {
                "status": "ok",
                "slices": slices_payload,
                "template_slices": template_slices_payload,
                "rules": rules_payload,
                "rule_audit": rule_audit_payload,
                "template_audit": template_audit_payload,
                "aggregated_risks": aggregate_payload,
                "annotated_file": annotate_payload,
                "revised_file": revision_payload,
                "summary": summary,
            }

            yield self.create_text_message(fmt("doc_slice_audit_template", "complete", label_lang))
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
            logger.exception("Doc slice template audit failed: %s", detail)
            for m in self._emit_error(None, None, detail):
                yield m
