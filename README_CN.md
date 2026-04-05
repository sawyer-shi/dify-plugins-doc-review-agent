# 文档审核Agent

一个强大的 Dify 插件，使用 AI 驱动的智能审核功能，支持标书、公文、合同、资料等各种类型的文档审核。支持智能文档解析、基于规则的审核、风险聚合和带批注的文档生成，具有专业级质量和灵活的配置选项。

## 版本信息

- **当前版本**: v0.0.1
- **发布日期**: 2026-04-05
- **兼容性**: Dify 插件框架
- **Python 版本**: 3.12

### 版本历史
- **v0.0.1** (2026-04-05): 初始版本，包含本地文档审核功能

## 快速开始

1. 在您的 Dify 环境中安装插件
2. 下载模板Workflwo：
 https://github.com/sawyer-shi/awsome-dify-agents/blob/master/src/doc-review-agent/agent_dsl/Document%20Review%20%E2%80%93%20Multi-threaded%20Processing%20Mode.yml
 <img width="1763" height="411" alt="sample00" src="https://github.com/user-attachments/assets/9d9c4fa9-3d4f-4b3b-acc6-7568b79096ca" />
 https://github.com/sawyer-shi/awsome-dify-agents/blob/master/src/doc-review-agent/agent_dsl/%E6%96%87%E6%A1%A3%E5%AE%A1%E6%A0%B8--%E5%A4%9A%E7%BA%BF%E7%A8%8B%E5%A4%84%E7%90%86%E6%A8%A1%E5%BC%8F.yml
 <img width="1802" height="568" alt="sample01" src="https://github.com/user-attachments/assets/dd229702-f736-4ad0-8b27-cd6bce99f113" />
3. 下载规则模板和样例文件：https://github.com/sawyer-shi/awsome-dify-agents/blob/master/src/doc-review-agent/agent_test_files/review_rules_research_en.csv 
4. 配置您的 LLM 模型设置
5. 上传你文档并开始审核流程
<img width="1816" height="832" alt="sample02" src="https://github.com/user-attachments/assets/1f0fa651-154e-4756-abde-634260b16b31" />

## 核心特性

- **智能文档解析**: 使用 LLM 指导将文档解析为可管理的切片
- **基于规则的审核**: 加载审核规则并根据规则审核文档切片
- **风险聚合**: 汇总和去重多个切片的审核风险
- **文档批注**: 生成带 AI 辅助批注的文档
- **灵活配置**: 支持自定义审核规则和审核级别
- **多种文档类型**: 支持标书、公文、合同和资料
- **批量处理**: 通过切片高效处理大型文档
- **LLM 集成**: 利用配置的 LLM 模型进行智能分析

## 核心功能

### 文档解析

#### 文档解析切片 (doc_slice_parser)
使用 LLM 指导将文档解析为审核切片。
- **功能特性**:
  - 基于内容结构的智能文档切片
  - 可配置的最大切片大小（默认：1200 字符）
  - 支持解析提示词以指导切片策略
  - LLM 辅助的切片边界检测
  - 针对 docx 格式文档优化

### 规则管理

#### 审核规则加载 (rule_loader)
根据文档摘要和审核要求加载审核规则。
- **功能特性**:
  - 基于文档类型的动态规则选择
  - 支持不同的审核级别（严格/宽松）
  - 针对特定场景的可自定义规则提示
  - 基于文档摘要的规则匹配
  - 灵活的规则配置

### 文档审核

#### 文档切片审核 (chunk_auditor)
使用加载的规则审核文档切片，采用双循环处理架构。
- **功能特性**:
  - 基于规则的风险检测，采用双循环架构
  - 详细的风险识别和分类
  - 基于引用的风险参考
  - 额外提示支持以增强审核
  - 多语言输出支持（中文、英文、日文、韩文、西班牙文、法文、德文、葡萄牙文、俄文、阿拉伯文）
  - 全面的切片级别分析
  - 内置切片和规则循环，高效处理

#### 文档切片审核--单循环 (chunk_auditor_slice)
对单个切片对象与规则集执行循环审核（仅规则循环，需要添加外循环）。
- **功能特性**:
  - 单个切片对象处理
  - 仅规则循环架构（切片处理一次，规则内部循环）
  - 需要外循环处理多个切片
  - 多语言输出支持（中文、英文、日文、韩文、西班牙文、法文、德文、葡萄牙文、俄文、阿拉伯文）
  - 自动语言检测能力
  - 优化批量处理工作流程

### 风险管理

#### 风险聚合器 (risk_aggregator)
汇总和去重多个切片的审核风险。
- **功能特性**:
  - 智能风险去重
  - 多种合并策略（按引用去重等）
  - 风险分类和优先级排序
  - 全面的风险摘要生成
  - 冲突解决策略

### 文档输出

#### 文档批注生成 (doc_annotator)
生成带 AI 辅助批注的文档输出。
- **功能特性**:
  - 批注风格的批注生成
  - 原始文档保留
  - 基于风险的批注插入
  - 可配置的输出文件命名
  - 支持 docx 格式输出

#### 文件修正 (file_revision)
处理 doc_annotator 生成的带批注文档，对同段原文的重叠风险批注进行合并，并可按批注修改原文且保留最新批注。
- **功能特性**:
  - 针对同一段原文多风险批注提供三种策略：
    - 按风险等级保留批注（同级用语义判定）
    - 按语义理解保留批注
    - 按语义理解综合批注（规则编号合并保留）
  - 可选是否按合并后/最新批注修改原文
  - 处理后始终保留最新批注
  - 兼容 doc_annotator 生成的 `[rule_code][severity]` 批注格式
  - 支持 docx 格式输出

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

### 文档审核工作流程

#### 步骤 1: 文档解析
使用**文档解析切片**工具解析您的文档：
- **参数**:
  - `upload_file`: 要解析的文档文件（仅 docx，必需）
  - `model_config`: 用于解析的 LLM 模型（必需）
  - `parse_hint`: 可选的解析策略提示
  - `max_chunk_chars`: 每个切片的建议最大字符数（默认：1200）

#### 步骤 2: 加载审核规则
使用**审核规则加载**工具加载适当的审核规则：
- **参数**:
  - `model_config`: 用于规则加载的 LLM 模型（必需）
  - `doc_summary`: 文档的摘要或预览
  - `audit_level`: 审核严格程度（strict/lenient，默认：strict）
  - `rule_hint`: 可选的规则选择提示

#### 步骤 3: 审核文档切片
使用**文档切片审核**工具审核每个文档切片：
- **参数**:
  - `model_config`: 用于审核的 LLM 模型（必需）
  - `chunk_text`: 要审核的文本切片（必需）
  - `chunk_id`: 切片标识符（必需）
  - `rules`: 来自规则加载器的规则文本
  - `extra_hint`: 可选的额外语境提示

#### 步骤 4: 汇总风险
使用**风险聚合器**工具合并审核结果：
- **参数**:
  - `model_config`: 用于聚合的 LLM 模型（必需）
  - `raw_results`: 来自多个切片的原始审核结果（必需）
  - `merge_policy`: 冲突解决策略（默认：dedupe_by_quote）

#### 步骤 5: 生成带批注的文档
使用**文档批注生成**工具创建最终输出：
- **参数**:
  - `model_config`: 用于批注的 LLM 模型（必需）
  - `upload_file`: 原始文档文件（仅 docx，必需）
  - `audit_report`: 汇总后的审核报告 JSON（必需）
  - `annotation_style`: 批注风格（默认：comment）
  - `output_file_name`: 不含扩展名的输出文件名

#### 步骤 6: 合并/修正文档
使用**文件修正**工具处理批注文档，合并重叠批注并可选修改原文：
- **参数**:
  - `model_config`: 用于语义合并/选择的 LLM 模型（必需）
  - `upload_file`: 文档批注生成工具输出的 docx（必需）
  - `merge_strategy`: `keep_highest_risk` / `keep_semantic` / `merge_semantic`（必需）
  - `apply_to_original`: `no`/`yes`（必填，默认：`no`）
  - `output_file_name`: 不含扩展名的输出文件名

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
