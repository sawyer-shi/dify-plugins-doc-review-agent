from collections.abc import Generator
import logging
from types import SimpleNamespace
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


logger = logging.getLogger(__name__)

WORD_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocSliceAuditTool(Tool):
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
        return SimpleNamespace(
            blob=blob_entry.get("blob", b""),
            filename=filename,
            name=filename,
            original_filename=filename,
        )

    def _emit_error(
        self,
        step_index: int | None,
        step_name: str | None,
        detail: str,
    ) -> list[ToolInvokeMessage]:
        payload: dict[str, Any]
        if step_name:
            text = f"❌ {step_name}失败: {detail}"
            payload = {
                "error": f"{step_name}失败",
                "detail": detail,
                "step": step_name,
            }
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
                    blobs.append(
                        {
                            "blob": getattr(message.message, "blob", b""),
                            "meta": message.meta or {},
                        }
                    )
        except Exception as e:
            return {"error": str(e)}

        if isinstance(last_json, dict) and last_json.get("error"):
            return {"error": self._error_detail(last_json, last_text)}

        if last_json is None and not blobs:
            return {"error": self._error_detail(last_json, last_text or "No structured output returned")}

        return {
            "payload": last_json,
            "blobs": blobs,
            "text": last_text,
        }

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        llm_model = tool_parameters.get("model_config")
        upload_file = tool_parameters.get("upload_file")
        rules_file = tool_parameters.get("rules_file")

        if not upload_file:
            logger.error("Missing required parameter: upload_file")
            yield self.create_text_message("❌ 请输入待审核文档文件 upload_file")
            yield self.create_json_message({"error": "No file uploaded", "field": "upload_file"})
            return

        if not rules_file:
            logger.error("Missing required parameter: rules_file")
            yield self.create_text_message("❌ 请输入审核规则文件 rules_file")
            yield self.create_json_message({"error": "rules_file is required", "field": "rules_file"})
            return

        if not isinstance(llm_model, dict):
            logger.error("Invalid model_config")
            yield self.create_text_message("❌ model_config invalid")
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

        annotate_output_name = f"annotated_{output_file_name}" if output_file_name else None
        revise_output_name = output_file_name or None

        steps = [
            (1, "文档切片"),
            (2, "规则加载"),
            (3, "分片审核"),
            (4, "风险聚合"),
            (5, "文档标注"),
            (6, "文件修订"),
        ]

        logger.info("Starting doc slice audit task")
        yield self.create_text_message("🚀 文档切片审核启动中...")

        try:
            step_index, step_name = steps[0]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}")
            logger.info("[%s/6] %s", step_index, step_name)
            parser_result = self._run_subtool(
                self._get_subtool_class("doc_slice_parser"),
                {
                    "model_config": llm_model,
                    "upload_file": upload_file,
                    "parse_hint": parse_hint,
                    "slice_strategy": slice_strategy,
                    "max_chunk_chars": max_chunk_chars,
                },
            )
            if parser_result.get("error"):
                for message in self._emit_error(step_index, step_name, str(parser_result["error"])):
                    yield message
                return
            slices_payload = parser_result.get("payload") or {}
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成")

            step_index, step_name = steps[1]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}")
            logger.info("[%s/6] %s", step_index, step_name)
            loader_result = self._run_subtool(self._get_subtool_class("rule_loader"), {"rules_file": rules_file})
            if loader_result.get("error"):
                for message in self._emit_error(step_index, step_name, str(loader_result["error"])):
                    yield message
                return
            rules_payload = loader_result.get("payload") or {}
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成")

            step_index, step_name = steps[2]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}")
            logger.info("[%s/6] %s", step_index, step_name)
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
                for message in self._emit_error(step_index, step_name, str(audit_result["error"])):
                    yield message
                return
            audit_payload = audit_result.get("payload") or {}
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成")

            step_index, step_name = steps[3]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}")
            logger.info("[%s/6] %s", step_index, step_name)
            aggregate_result = self._run_subtool(
                self._get_subtool_class("risk_aggregator"),
                {
                    "model_config": llm_model,
                    "raw_results": audit_payload,
                    "merge_policy": merge_policy,
                },
            )
            if aggregate_result.get("error"):
                for message in self._emit_error(step_index, step_name, str(aggregate_result["error"])):
                    yield message
                return
            aggregate_payload = aggregate_result.get("payload") or {}
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成")

            step_index, step_name = steps[4]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}")
            logger.info("[%s/6] %s", step_index, step_name)
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
                for message in self._emit_error(step_index, step_name, str(annotate_result["error"])):
                    yield message
                return
            annotate_payload = annotate_result.get("payload") or {}
            annotate_blobs = annotate_result.get("blobs") or []
            if not annotate_blobs:
                for message in self._emit_error(step_index, step_name, "标注文档未生成"):
                    yield message
                return
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成")

            step_index, step_name = steps[5]
            yield self.create_text_message(f"{step_index}/6 正在执行：{step_name}")
            logger.info("[%s/6] %s", step_index, step_name)
            revision_input_file = self._blob_to_file(annotate_blobs[0], "annotated.docx")
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
                for message in self._emit_error(step_index, step_name, str(revision_result["error"])):
                    yield message
                return
            revision_payload = revision_result.get("payload") or {}
            revision_blobs = revision_result.get("blobs") or []
            if not revision_blobs:
                for message in self._emit_error(step_index, step_name, "修订文档未生成"):
                    yield message
                return
            yield self.create_text_message(f"✅ {step_index}/6 {step_name}完成")

            summary_payload = {
                "status": "ok",
                "slices": slices_payload,
                "rules": rules_payload,
                "audit": audit_payload,
                "aggregated_risks": aggregate_payload,
                "annotated_file": annotate_payload,
                "revised_file": revision_payload,
                "summary": {
                    "chunk_count": len(slices_payload.get("chunks", [])) if isinstance(slices_payload, dict) else 0,
                    "rule_count": (
                        int(rules_payload.get("rule_count", 0))
                        if isinstance(rules_payload, dict) and str(rules_payload.get("rule_count", "")).isdigit()
                        else len(rules_payload.get("rules", []))
                        if isinstance(rules_payload, dict)
                        else 0
                    ),
                    "total_pairs": int(audit_payload.get("total_pairs", 0)) if isinstance(audit_payload, dict) else 0,
                    "total_hits": (
                        int(aggregate_payload.get("summary", {}).get("output_hits", 0))
                        if isinstance(aggregate_payload, dict) and isinstance(aggregate_payload.get("summary"), dict)
                        else int(audit_payload.get("total_hits", 0))
                        if isinstance(audit_payload, dict)
                        else 0
                    ),
                    "annotation_count": int(annotate_payload.get("annotation_count", 0)) if isinstance(annotate_payload, dict) else 0,
                    "final_comment_count": int(revision_payload.get("final_comment_count", 0)) if isinstance(revision_payload, dict) else 0,
                    "modified_count": int(revision_payload.get("modified_count", 0)) if isinstance(revision_payload, dict) else 0,
                },
            }
            yield self.create_text_message("🎯 文档切片审核完成！")
            yield self.create_json_message(summary_payload)

            for blob_entry in annotate_blobs:
                yield self.create_blob_message(blob=blob_entry.get("blob", b""), meta=blob_entry.get("meta") or {"mime_type": WORD_MIME_TYPE})
            for blob_entry in revision_blobs:
                yield self.create_blob_message(blob=blob_entry.get("blob", b""), meta=blob_entry.get("meta") or {"mime_type": WORD_MIME_TYPE})
            logger.info("Doc slice audit task completed")

        except Exception as e:
            detail = str(e)
            logger.exception("Doc slice audit task failed: %s", detail)
            for message in self._emit_error(None, None, f"文档切片审核执行异常: {detail}"):
                yield message
