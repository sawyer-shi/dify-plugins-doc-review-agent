# Document Review Agent

A powerful Dify plugin providing comprehensive AI-powered document review capabilities for various types of documents including tender documents, official documents, contracts, and materials, with support for non-compliant document detection. Supports intelligent document parsing, rule-based auditing, risk aggregation, and annotated document generation with professional-grade quality and flexible configuration options.

## Version Information

- **Current Version**: v0.0.2
- **Release Date**: 2026-04-13
- **Compatibility**: Dify Plugin Framework
- **Python Version**: 3.12

### Version History
- **v0.0.2** (2026-04-13):
  - Added integrated **slice audit tool** `doc-slice-audit` (parse -> load rules -> audit -> aggregate -> annotate -> revise)
  - Added integrated **simple/full-text audit tool** `doc-audit` for short document single-loop auditing
  - Added **template slice audit tool** `doc-slice-audit-template` with required `template_file` and optional `rules_file`
  - Added **template full-text audit tool** `doc-audit-template` with required `template_file` and optional `rules_file`
  - Added template comparators: `template_chunk_auditor.py` and `template_doc_auditor.py`
  - Added template risk code normalization to `template-0001` style and aligned output fields for aggregation/annotation
  - Improved no-risk handling in `doc_annotator` (returns original reviewed file with `annotation_count=0` instead of failing)
  - Reorganized provider tool exposure and YAML definitions around integrated top-level tools
- **v0.0.1** (2026-04-05): Initial release with local document review capabilities

## Quick Start

1. Install plugin in your Dify environment

2. Download Rules Template and Sample Files:
   https://github.com/sawyer-shi/awsome-dify-agents/blob/master/src/doc-review-agent/agent_test_files/review_rules_research_en.csv

. Configure your LLM model settings. Also note: To prevent timeout, you can modify the parameter PLUGIN_MAX_EXECUTION_TIMEOUT to increase processing time!!!

4. Upload your document and start the review process. Results are as follows:
   <img width="1816" height="832" alt="sample02" src="https://github.com/user-attachments/assets/1f0fa651-154e-4756-abde-634260b16b31" />

## Key Features

- **Four Integrated Audit Tools**: Slice/non-template, full-text/non-template, slice/template, and full-text/template workflows
- **Template Baseline Review**: Template-based findings use normalized risk codes like `template-0001` for consistent downstream tagging
- **Hybrid Rule + Template Aggregation**: Optional `rules_file` can run together with template audit and merge into one unified risk payload
- **Structured Risk Pipeline**: Audit -> aggregation -> annotation -> revision with consistent data schema across workflows
- **High-Quality Output Files**: Reviewed (annotated) and revised `.docx` outputs with configurable JSON/file output modes
- **Flexible Control Knobs**: Slice strategy, audit strategy, merge policy, merge strategy, language, and output settings
- **No-Risk Safe Handling**: When no risks are found, the workflow returns a valid reviewed file instead of failing
- **Multi-Language Reasoning**: Supports zh/en/ja/ko/es/fr/de/pt/ru/ar outputs

  <img width="409" height="684" alt="EN" src="https://github.com/user-attachments/assets/097c6095-2c9f-45be-ba57-eba41b396d84" /><img width="411" height="644" alt="CN" src="https://github.com/user-attachments/assets/e7db9fb0-6780-4c3e-b39d-98a40dee74a2" />

## Core Features

### 1) Doc Slice Audit (`doc-slice-audit`)
Integrated non-template slice auditing for larger documents.
- **Required**: `model_config`, `upload_file`, `rules_file`
- **What it does (6 steps)**:
  1. Document slicing
  2. Rule loading
  3. Chunk auditing
  4. Risk aggregation
  5. Document annotation
  6. File revision
- **Best for**: contracts/tenders where chunk-level analysis is preferred

### 2) Doc Audit (`doc-audit`)
Integrated non-template full-text auditing for short documents.
- **Required**: `model_config`, `upload_file`, `rules_file`
- **What it does (6 steps)**:
  1. Load review document
  2. Rule loading
  3. Full-text rule audit
  4. Risk aggregation
  5. Document annotation
  6. File revision
- **Best for**: shorter documents where whole-text context is important

### 3) Doc Slice Audit Template (`doc-slice-audit-template`)
Integrated template-based slice auditing.
- **Required**: `model_config`, `upload_file`, `template_file`
- **Optional**: `rules_file` (runs rule audit + template audit together when provided)
- **What it does (8-step pipeline)**:
  1. Slice review document
  2. Slice template document
  3. Rule loading (optional input; step kept in progress output)
  4. Rule-based chunk audit (runs when `rules_file` is provided, otherwise marked as skipped)
  5. Template chunk comparison audit
  6. Risk aggregation
  7. Document annotation
  8. File revision
- **Output semantics**: template findings use normalized codes (`template-0001`, `template-0002`, ...), severity from LLM (`high|medium|low`)

### 4) Doc Audit Template (`doc-audit-template`)
Integrated template-based full-text auditing.
- **Required**: `model_config`, `upload_file`, `template_file`
- **Optional**: `rules_file` (runs rule audit + template audit together when provided)
- **What it does (8-step pipeline)**:
  1. Load review document
  2. Load template document
  3. Rule loading (optional input; step kept in progress output)
  4. Rule-based full-text audit (runs when `rules_file` is provided, otherwise marked as skipped)
  5. Full-text template comparison audit
  6. Risk aggregation
  7. Document annotation
  8. File revision
- **Best for**: short-form baseline checks against a model template

### Shared Output and Controls
- **JSON output**: `summary_only` or `detailed`
- **File output**: revised only, or reviewed + revised
- **Revision behavior**: choose merge strategy and whether to apply revisions back to source text
- **No-risk behavior**: returns a valid reviewed file with `annotation_count=0`

## Technical Advantages

- **LLM-Powered Analysis**: Leverages advanced LLM models for intelligent document understanding
- **Rule-Based Auditing**: Flexible rule system for customizable review criteria
- **Chunk-Based Processing**: Efficient handling of large documents through intelligent slicing
- **Risk Deduplication**: Smart aggregation to eliminate redundant findings
- **Annotated Output**: Professional document output with clear risk indicators
- **Multi-Format Support**: Optimized for docx format with extensibility for other formats
- **Configurable Audit Levels**: Support for strict and lenient auditing modes
- **Real-Time Processing**: Efficient workflow for timely document review

## Requirements

- Python 3.12
- Dify Platform access
- Configured LLM model
- Required Python packages (installed via requirements.txt):
  - dify_plugin>=0.5.0
  - python-docx>=1.1.2
  - openpyxl>=3.1.5

## Installation & Configuration

1. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure your LLM model in plugin settings

3. Install plugin in your Dify environment

## Usage

### Choose the Right Tool

#### A) Non-template Slice Audit
Use `doc-slice-audit` when you have a rule file and need chunk-level review.
- Required: `model_config`, `upload_file`, `rules_file`
- Recommended options: `slice_strategy`, `max_chunk_chars`, `merge_policy`, `output_language`

#### B) Non-template Full-Text Audit
Use `doc-audit` when you have a rule file and the document is short enough for full-text auditing.
- Required: `model_config`, `upload_file`, `rules_file`
- Recommended options: `audit_strategy`, `merge_policy`, `output_language`

#### C) Template Slice Audit
Use `doc-slice-audit-template` when template compliance is required at chunk level.
- Required: `model_config`, `upload_file`, `template_file`
- Optional: `rules_file` for hybrid rule + template audit
- Notes: template findings are normalized to `template-0001` style risk codes

#### D) Template Full-Text Audit
Use `doc-audit-template` when template compliance is required for the full document.
- Required: `model_config`, `upload_file`, `template_file`
- Optional: `rules_file` for hybrid rule + template audit

### Typical Output
- A JSON summary (or detailed JSON if enabled)
- A reviewed `.docx` (annotations)
- A revised `.docx` (merged or applied revisions)

## Supported Document Formats

- **Input**: .docx (Microsoft Word)
- **Output**: .docx (Microsoft Word with annotations)

## Notes

- Document parsing is optimized for docx format
- Chunk size can be adjusted based on document complexity
- Audit level affects the strictness of rule application
- Risk aggregation uses intelligent deduplication to avoid redundant findings
- Annotation style currently supports comment-based annotations
- Large documents are processed efficiently through chunking
- All tools require a configured LLM model for operation

## Developer Information

- **Author**: `https://github.com/sawyer-shi`
- **Email**: sawyer36@foxmail.com
- **License**: Apache License 2.0
- **Source Code**: `https://github.com/sawyer-shi/dify-plugins-doc-review-agent`
- **Support**: Through Dify platform and GitHub Issues

## License Notice

This project is licensed under Apache License 2.0. See [LICENSE](LICENSE) file for full license text.

---

**Ready to review your documents with AI-powered intelligence?**
