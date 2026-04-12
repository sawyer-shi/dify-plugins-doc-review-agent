# Document Review Agent

A powerful Dify plugin providing comprehensive AI-powered document review capabilities for various types of documents including tender documents, official documents, contracts, and materials. Supports intelligent document parsing, rule-based auditing, risk aggregation, and annotated document generation with professional-grade quality and flexible configuration options.

## Version Information

- **Current Version**: v0.0.2
- **Release Date**: 2026-04-05
- **Compatibility**: Dify Plugin Framework
- **Python Version**: 3.12

### Version History
- **v0.0.1** (2026-04-05): Initial release with local document review capabilities

## Quick Start

1. Install plugin in your Dify environment
2. Download Template Workflow:
   
   English：https://github.com/sawyer-shi/awsome-dify-agents/blob/master/src/doc-review-agent/agent_dsl/Document%20Review%20%E2%80%93%20Multi-threaded%20Processing%20Mode.yml

   <img width="1763" height="411" alt="sample00" src="https://github.com/user-attachments/assets/9d9c4fa9-3d4f-4b3b-acc6-7568b79096ca" />
   
   Chinese：https://github.com/sawyer-shi/awsome-dify-agents/blob/master/src/doc-review-agent/agent_dsl/%E6%96%87%E6%A1%A3%E5%AE%A1%E6%A0%B8--%E5%A4%9A%E7%BA%BF%E7%A8%8B%E5%A4%84%E7%90%86%E6%A8%A1%E5%BC%8F.yml

   <img width="1802" height="568" alt="sample01" src="https://github.com/user-attachments/assets/dd229702-f736-4ad0-8b27-cd6bce99f113" />
3. Download Rules Template and Sample Files:
   https://github.com/sawyer-shi/awsome-dify-agents/blob/master/src/doc-review-agent/agent_test_files/review_rules_research_en.csv

4. Configure your LLM model settings. Also note: To prevent timeout, you can modify the parameter PLUGIN_MAX_EXECUTION_TIMEOUT to increase processing time!!!

5. Upload your document and start the review process. Results are as follows:
   <img width="1816" height="832" alt="sample02" src="https://github.com/user-attachments/assets/1f0fa651-154e-4756-abde-634260b16b31" />

## Key Features

- **Intelligent Document Parsing**: Parse and slice documents into manageable chunks using LLM guidance
- **Rule-Based Auditing**: Load review rules and audit document chunks against them
- **Risk Aggregation**: Aggregate and deduplicate audit risks from multiple chunks
- **Document Annotation**: Generate annotated documents with AI-assisted comments
- **Flexible Configuration**: Support for custom review rules and audit levels
- **Multiple Document Types**: Supports tender documents, official documents, contracts, and materials
- **Batch Processing**: Efficient processing of large documents through chunking
- **LLM Integration**: Leverages configured LLM models for intelligent analysis

  <img width="409" height="684" alt="EN" src="https://github.com/user-attachments/assets/097c6095-2c9f-45be-ba57-eba41b396d84" /><img width="411" height="644" alt="CN" src="https://github.com/user-attachments/assets/e7db9fb0-6780-4c3e-b39d-98a40dee74a2" />

## Core Features

### Document Parsing

#### Doc Slice Parser (doc_slice_parser)
Parse and slice a document into review chunks using LLM guidance.
- **Features**:
  - Intelligent document slicing based on content structure
  - Configurable maximum chunk size (default: 1200 characters)
  - Support for parse hints to guide slicing strategy
  - LLM-assisted chunk boundary detection
  - Optimized for docx format documents

### Rule Management

#### Rule Loader (rule_loader)
Load review rules based on document summary and audit requirements.
- **Features**:
  - Dynamic rule selection based on document type
  - Support for different audit levels (strict/lenient)
  - Customizable rule hints for specific scenarios
  - Document summary-based rule matching
  - Flexible rule configuration

### Document Auditing

#### Chunk Auditor (chunk_auditor)
Audit a document chunk with loaded rules using dual-loop processing.
- **Features**:
  - Rule-based risk detection with dual-loop architecture
  - Detailed risk identification and categorization
  - Quote-based risk referencing
  - Extra hint support for enhanced auditing
  - Multi-language output support (Chinese, English, Japanese, Korean, Spanish, French, German, Portuguese, Russian, Arabic)
  - Comprehensive chunk-level analysis
  - Built-in chunk and rule loops for efficient processing

#### Chunk Auditor Slice (chunk_auditor_slice)
Audit a single chunk object against all rules using rule-loop only (requires outer loop).
- **Features**:
  - Single chunk object processing
  - Rule-loop only architecture (chunk processed once, rules loop internally)
  - Requires outer loop for multiple chunks
  - Multi-language output support (Chinese, English, Japanese, Korean, Spanish, French, German, Portuguese, Russian, Arabic)
  - Auto language detection capability
  - Optimized for batch processing workflows

### Risk Management

#### Risk Aggregator (risk_aggregator)
Aggregate and deduplicate audit risks from multiple chunks.
- **Features**:
  - Intelligent risk deduplication
  - Multiple merge policies (dedupe_by_quote, etc.)
  - Risk categorization and prioritization
  - Comprehensive risk summary generation
  - Conflict resolution strategies

### Document Output

#### Doc Annotator (doc_annotator)
Generate annotated document output with LLM-assisted notes.
- **Features**:
  - Comment-style annotation generation
  - Original document preservation
  - Risk-based comment insertion
  - Configurable output file naming
  - Support for docx format output

#### File Revision (file_revision)
Process the annotated docx generated by doc_annotator, merge overlapping comments, and optionally revise original text while keeping latest comments.
- **Features**:
  - Three merge strategies for multi-risk comments on the same original text:
    - Keep highest risk (tie broken by semantic selection)
    - Keep semantic best
    - Semantic merge with combined rule codes
  - Optional source-text revision based on merged/latest comments
  - Latest comments are always retained after processing
  - Compatible with doc_annotator comment format `[rule_code][severity]`
  - Support for docx format output

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

### Document Review Workflow

#### Step 1: Document Parsing
Use **Doc Slice Parser** to parse your document:
- **Parameters**:
  - `upload_file`: The document file to parse (docx only, required)
  - `model_config`: The LLM model to use for parsing (required)
  - `parse_hint`: Optional hint for parsing strategy
  - `max_chunk_chars`: Suggested max characters per chunk (default: 1200)

#### Step 2: Load Review Rules
Use **Rule Loader** to load appropriate review rules:
- **Parameters**:
  - `model_config`: The LLM model to use for rule loading (required)
  - `doc_summary`: Summary or preview of the document
  - `audit_level`: Audit strictness (strict/lenient, default: strict)
  - `rule_hint`: Optional hint for rule selection

#### Step 3: Audit Document Chunks
Use **Chunk Auditor** to audit each document chunk:
- **Parameters**:
  - `model_config`: The LLM model to use for auditing (required)
  - `chunk_text`: The text chunk to review (required)
  - `chunk_id`: Chunk identifier (required)
  - `rules`: Rules text from Rule Loader
  - `extra_hint`: Optional extra hint

#### Step 4: Aggregate Risks
Use **Risk Aggregator** to combine audit results:
- **Parameters**:
  - `model_config`: The LLM model to use for aggregation (required)
  - `raw_results`: Raw audit results from multiple chunks (required)
  - `merge_policy`: Policy for conflict resolution (default: dedupe_by_quote)

#### Step 5: Generate Annotated Document
Use **Doc Annotator** to create the final output:
- **Parameters**:
  - `model_config`: The LLM model to use for annotations (required)
  - `upload_file`: The original document file (docx only, required)
  - `audit_report`: The aggregated audit report JSON (required)
  - `annotation_style`: Annotation style (default: comment)
  - `output_file_name`: The output file name without extension

#### Step 6: Merge/Revise Annotated File
Use **File Revision** to merge overlapping comments and optionally revise source text:
- **Parameters**:
  - `model_config`: The LLM model for semantic merge/selection (required)
  - `upload_file`: The docx generated by Doc Annotator (required)
  - `merge_strategy`: `keep_highest_risk` / `keep_semantic` / `merge_semantic` (required)
  - `apply_to_original`: `no`/`yes` (required, default: `no`)
  - `output_file_name`: The output file name without extension

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
