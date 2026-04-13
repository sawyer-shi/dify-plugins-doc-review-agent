# 文档审核Agent

一个强大的 Dify 插件，使用 AI 驱动的智能审核功能，支持标书、公文、合同、资料等各种类型的文档审核(支持范本和非范本文档审核)。支持智能文档解析、基于规则的审核、风险聚合和带批注的文档生成，具有专业级质量和灵活的配置选项。

## 版本信息

- **当前版本**: v0.0.2
- **发布日期**: 2026-04-13
- **兼容性**: Dify 插件框架
- **Python 版本**: 3.12

### 版本历史
- **v0.0.2** (2026-04-13):
  - 新增一体化**切片审核工具** `doc-slice-audit`（切片 -> 规则加载 -> 审核 -> 聚合 -> 批注 -> 修订）
  - 新增一体化**简单/全文审核工具** `doc-audit`，适用于短文档单循环审核
  - 新增**范本切片审核工具** `doc-slice-audit-template`，`template_file` 必填、`rules_file` 可选
  - 新增**范本全文审核工具** `doc-audit-template`，`template_file` 必填、`rules_file` 可选
  - 新增范本对比子能力：`template_chunk_auditor.py` 和 `template_doc_auditor.py`
  - 新增范本风险编号规范 `template-0001` 格式，并统一聚合/标注字段结构
  - 优化 `doc_annotator` 无风险场景处理（不再报错，直接返回 `annotation_count=0` 的已审核文档）
  - 按一体化顶层工具重构 Provider 工具暴露与 YAML 配置
- **v0.0.1** (2026-04-05): 初始版本，包含本地文档审核功能

## 快速开始

1. 在您的 Dify 环境中安装插件

2. 下载规则模板和样例文件：
   https://github.com/sawyer-shi/awsome-dify-agents/blob/master/src/doc-review-agent/agent_test_files/review_rules_research_en.csv

3. 配置您的 LLM 模型设置。另外注意：防止超时可以修改参数PLUGIN_MAX_EXECUTION_TIMEOUT来增加处理时间，防止超时！！！

4. 上传你文档并开始审核流程结果如下：
   <img width="1816" height="832" alt="sample02" src="https://github.com/user-attachments/assets/1f0fa651-154e-4756-abde-634260b16b31" />

## 核心特性

- **四类一体化审核工具**: 覆盖切片/全文、非范本/范本四种主流程
- **范本基线审核能力**: 以范本文档为基线对比，范本风险编号统一为 `template-0001` 风格
- **规则+范本混合审核**: `rules_file` 可选叠加，规则结果与范本结果统一聚合
- **结构化风险处理链路**: 审核 -> 聚合 -> 批注 -> 修订，字段结构一致便于后续打标
- **高质量文档输出**: 支持已审核（批注）与修订稿输出，并支持 JSON 摘要/明细模式
- **灵活参数控制**: 支持切片策略、审核策略、合并策略、输出语言与输出模式
- **无风险场景稳定返回**: 无命中时不报错，返回 `annotation_count=0` 的有效已审核文档
- **多语言输出支持**: 支持中/英/日/韩/西/法/德/葡/俄/阿

  <img width="409" height="684" alt="EN" src="https://github.com/user-attachments/assets/097c6095-2c9f-45be-ba57-eba41b396d84" /><img width="411" height="644" alt="CN" src="https://github.com/user-attachments/assets/e7db9fb0-6780-4c3e-b39d-98a40dee74a2" />



## 核心功能

### 1) 文档审核--切片审核（非范本）`doc-slice-audit`
面向较长文档的非范本切片审核。
- **必填**：`model_config`、`upload_file`、`rules_file`
- **执行流程（6步）**：
  1. 文档切片
  2. 规则加载
  3. 切片审核
  4. 风险聚合
  5. 文档批注
  6. 文件修订
- **适用场景**：合同/标书等需要分片审阅的文档

### 2) 文档审核--简单审核（非范本）`doc-audit`
面向短文档的非范本全文审核。
- **必填**：`model_config`、`upload_file`、`rules_file`
- **执行流程（6步）**：
  1. 加载审核文档
  2. 规则加载
  3. 全文规则审核
  4. 风险聚合
  5. 文档批注
  6. 文件修订
- **适用场景**：篇幅较短、需要全文上下文判断的文档

### 3) 文档审核--切片审核（范本）`doc-slice-audit-template`
面向较长文档的范本切片审核。
- **必填**：`model_config`、`upload_file`、`template_file`
- **可选**：`rules_file`（提供后执行规则审核+范本审核的混合流程）
- **执行流程（8步）**：
  1. 审核文档切片
  2. 范本文档切片
  3. 规则加载（可选输入；进度步骤始终保留）
  4. 规则分片审核（提供 `rules_file` 时执行，否则标记为跳过）
  5. 范本分片对比审核
  6. 风险聚合
  7. 文档标注
  8. 文件修订
- **输出语义**：范本风险编号统一为 `template-0001`、`template-0002`，风险等级由模型判定

### 4) 文档审核--简单审核（范本）`doc-audit-template`
面向短文档的范本全文审核。
- **必填**：`model_config`、`upload_file`、`template_file`
- **可选**：`rules_file`（提供后执行规则审核+范本审核的混合流程）
- **执行流程（8步）**：
  1. 加载审核文档
  2. 加载范本文档
  3. 规则加载（可选输入；进度步骤始终保留）
  4. 规则审核（提供 `rules_file` 时执行，否则标记为跳过）
  5. 范本对比审核
  6. 风险聚合
  7. 文档标注
  8. 文件修订
- **适用场景**：短文档的快速范本合规检查

### 通用输出与控制项
- **JSON 输出**：`summary_only` 或 `detailed`
- **文件输出**：仅修订稿，或“已审核稿 + 修订稿”
- **修订策略**：支持 `keep_highest_risk` / `keep_semantic` / `merge_semantic`
- **无风险返回**：无命中时返回有效已审核文档，`annotation_count=0`

## 技术优势

- **LLM 驱动分析**: 利用先进的 LLM 模型进行智能文档理解
- **基于规则的审核**: 灵活的规则系统用于可自定义的审核标准
- **基于切片的处理**: 通过智能切片高效处理大型文档
- **风险去重**: 智能聚合以消除重复发现
- **带批注的输出**: 带有清晰风险指示器的专业文档输出
- **多格式支持**: 针对 docx 格式优化，可扩展到其他格式
- **可配置的审核级别**: 支持严格和宽松的审核模式
- **实时处理**: 高效的工作流程，及时进行文档审核

## 系统要求

- Python 3.12
- Dify 平台访问权限
- 配置的 LLM 模型
- 所需的 Python 包（通过 requirements.txt 安装）:
  - dify_plugin>=0.5.0
  - python-docx>=1.1.2
  - openpyxl>=3.1.5

## 安装与配置

1. 安装所需的依赖项：
   ```bash
   pip install -r requirements.txt
   ```

2. 在插件设置中配置您的 LLM 模型

3. 在您的 Dify 环境中安装插件

## 使用方法

### 如何选择工具

#### A) 非范本切片审核
使用 `doc-slice-audit`（有规则文件、需要切片级审核）。
- 必填：`model_config`、`upload_file`、`rules_file`
- 推荐可选：`slice_strategy`、`max_chunk_chars`、`merge_policy`、`output_language`

#### B) 非范本全文审核
使用 `doc-audit`（有规则文件、文档较短）。
- 必填：`model_config`、`upload_file`、`rules_file`
- 推荐可选：`audit_strategy`、`merge_policy`、`output_language`

#### C) 范本切片审核
使用 `doc-slice-audit-template`（按范本逐段对比）。
- 必填：`model_config`、`upload_file`、`template_file`
- 可选：`rules_file`（启用规则+范本混合审核）
- 说明：范本风险会生成 `template-0001` 风格编号

#### D) 范本全文审核
使用 `doc-audit-template`（按范本做全文对比）。
- 必填：`model_config`、`upload_file`、`template_file`
- 可选：`rules_file`（启用规则+范本混合审核）

### 典型输出
- JSON 摘要（或明细 JSON）
- 已审核文档 `.docx`（含批注）
- 修订文档 `.docx`（按策略合并/回写）

## 支持的文档格式

- **输入**: .docx（Microsoft Word）
- **输出**: .docx（带批注的 Microsoft Word）

## 注意事项

- 文档解析针对 docx 格式优化
- 切片大小可以根据文档复杂度调整
- 审核级别影响规则应用的严格程度
- 风险聚合使用智能去重以避免重复发现
- 批注风格目前支持基于批注的批注
- 大型文档通过切片高效处理
- 所有工具都需要配置的 LLM 模型才能运行

## 开发者信息

- **作者**: `https://github.com/sawyer-shi`
- **邮箱**: sawyer36@foxmail.com
- **许可证**: Apache License 2.0
- **源代码**: `https://github.com/sawyer-shi/dify-plugins-doc-review-agent`
- **支持**: 通过 Dify 平台和 GitHub Issues 提供

## 许可证声明

本项目采用 Apache License 2.0 许可证。完整的许可证文本请参阅 [LICENSE](LICENSE) 文件。

---

**准备好使用 AI 驱动的智能审核您的文档了吗？**
