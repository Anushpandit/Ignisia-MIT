# Ignisia-MIT

Multi-Format Knowledge Retrieval Agent for SME Operations.

Ignisia-MIT is a hackathon MVP for teams that need to search across fragmented business knowledge stored in PDFs, emails, spreadsheets, text files, and scanned images. The current project focuses on the ingestion side of the pipeline: parsing documents, chunking them with source-aware metadata, and preparing them for embeddings and vector search.

## Problem

SME teams often lose time searching through documents scattered across inboxes, reports, spreadsheets, and image-based records. Even when the information exists, it is difficult to:

- find the right file quickly
- know which file a fact came from
- compare older and newer documents when they disagree

This MVP is designed to standardize those files into a retrieval-ready format so downstream search, citation, and conflict-resolution layers can work reliably.

## MVP Status

### Working now

- Multi-format parsing in `parser.py`
- Token-aware chunking in `chunker.py`
- Sample parsed outputs in `data/*.md`
- Sample chunk outputs in `data/*-chunks.json`
- Flask auth backend in `backend/`
- Vanilla TypeScript login and signup UI in `frontend/`

### Planned next

- embedding generation
- vector database integration
- retrieval API
- conflict detection across source documents
- cited answer generation with an LLM

## Architecture

### Knowledge Ingestion Pipeline

```text
Customer Uploads Files
    |
    v
parser.py
  - PDF parsing via LiteParse
  - email body + attachment extraction
  - spreadsheet extraction
  - image OCR
  - normalized ParsedDocument output
    |
    v
chunker.py
  - token-aware splitting
  - file-type-specific chunking
  - source-aware metadata
  - customer isolation via customer_id
    |
    v
embedder.py (planned)
    |
    v
Vector DB: ChromaDB / Pinecone (planned)
    |
    v
Retriever + Conflict Resolver (planned)
    |
    v
LLM Answer Layer (planned)
```

### App Layer

```text
Frontend (Login / Signup / Role Dashboards)
    |
    v
Flask Backend
    |
    v
SQLite User Store
```

## LiteParser In Action

The parser uses LiteParse for PDF extraction and image OCR. The image below is included to visually show the LiteParse-based document parsing stage in the MVP workflow.

![LiteParser demo](assets/liteparser-demo.webp)

## Supported File Types

| File Type | Status | Notes |
| --- | --- | --- |
| PDF | Supported | Parsed with LiteParse |
| Text / Markdown | Supported | Blank-line sectioning |
| Email (`.eml`) | Supported | Body extraction plus attachment metadata |
| Spreadsheet (`.csv`) | Supported | CSV rows normalized into structured tables |
| Spreadsheet (`.xlsx`) | Supported | Parsed with `openpyxl` |
| Image (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`) | Supported | OCR path available for PNG and JPEG in current parser |
| Outlook `.msg` | Not yet supported | Use `.eml` for now |
| Legacy `.xls` | Not yet supported | Use `.csv` or `.xlsx` |

## Current Project Structure

```text
backend/      Flask auth API, SQLite setup, bcrypt helpers
frontend/     Login and signup page in vanilla TypeScript
pages/        Customer and employee placeholder dashboards
examples/     Sample input files for parsing and chunking
data/         Saved parsed outputs and generated chunk outputs
assets/       README assets, including LiteParser image
parser.py     Multi-format parser
chunker.py    Chunking layer between parser and embeddings
test_chunker.py
```

## How Parsing And Chunking Work

### `parser.py`

`parser.py` reads an uploaded file and converts it into a normalized `ParsedDocument` object. That object contains:

- full extracted text
- metadata such as filename and date
- section-level content
- table data for spreadsheets
- attachment information for emails

### `chunker.py`

`chunker.py` takes a parsed document and breaks it into smaller retrieval units called chunks. Each chunk carries metadata that helps downstream search and conflict detection.

Every chunk includes:

- `customer_id`
- `source_file`
- `source_type`
- `document_date`
- `block_type`
- `heading_context`

This allows the future retrieval layer to:

- keep customer data isolated
- preserve source attribution
- compare different files by date
- trace answers back to the original document

## Example Outputs

### Parsed markdown outputs

- `data/sample-report.md`
- `data/sample-email.md`
- `data/sample-ocr-image.md`

### Chunk outputs

- `data/sample-report-chunks.json`
- `data/sample-email-chunks.json`
- `data/sample-ocr-image-chunks.json`

## Authentication Module

The project also includes a basic auth flow for customer and employee roles:

- signup and login UI in `frontend/`
- Flask API in `backend/app.py`
- SQLite persistence in `backend/database.py`
- bcrypt password hashing in `backend/auth.py`

Successful logins redirect users to role-specific placeholder pages in `pages/`.

## Run The Project

### 1. Install dependencies

```bash
uv sync
```

### 2. Start the backend

```bash
uv run python backend/app.py
```

### 3. Serve the frontend

```bash
uv run python -m http.server 5500
```

Open:

```text
http://127.0.0.1:5500/frontend/index.html
```

## Run The Chunking Tests

```bash
uv run python -m unittest test_chunker.py
```

## Known Limitations

- embeddings are not built yet
- vector database integration is not built yet
- conflict resolution is not built yet
- `.msg` emails are not supported yet
- `.xls` spreadsheets are not supported yet
- email attachment chunking currently uses attachment text fallback unless a nested parsed attachment document is available

## Roadmap

- add embedder module
- add ChromaDB or Pinecone integration
- add retrieval API
- add date-aware conflict detection
- add answer generation with citations
- connect the full ingestion and retrieval pipeline to the app UI
