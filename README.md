# Ignisia-MIT

Problem Statement 1: Multi-Format Knowledge Retrieval Agent for SME Operations.

Ignisia-MIT is a local-first RAG application for support and operations workflows. It ingests mixed business documents, embeds them into a customer-isolated ChromaDB store, and uses Groq to generate grounded answers with source context. On top of the retrieval pipeline, the project includes a working ticketing app with customer and employee dashboards, ticket chat, file uploads, email history, and a CRM support-ticket autofill agent.

## What The Project Does

This project is designed for teams that need to search and act on fragmented knowledge spread across:

- PDFs
- text and markdown files
- email files (`.eml`)
- spreadsheets (`.csv`, `.xlsx`)
- scanned or image-based documents

The app supports two main usage modes:

- Customer support workflow:
  customers create tickets, upload supporting files, and chat in a ticket thread
- Internal retrieval workflow:
  employees review tickets, ask retrieval-backed questions, inspect source references, and close tickets

The current build also includes a CRM support assistant page that can:

- read recent ticket history
- read email history already sent to a customer
- retrieve relevant customer-uploaded document chunks
- suggest issue summary, category, context, reasoning, and a draft resolution
- close the selected ticket and write a resolution email into customer email history

## Core Features

### Retrieval pipeline

- Multi-format parsing in [`parser.py`](parser.py)
- Token-aware chunking in [`chunker.py`](chunker.py)
- Local embedding generation in [`embedder.py`](embedder.py)
- Persistent ChromaDB storage in [`chroma_db/`](chroma_db)
- Customer-isolated retrieval collections
- Groq-backed answer generation in [`rag.py`](rag.py)
- Source references with file/date context
- Date-aware conflict handling and recency prioritization

### Application workflow

- Authentication for `employee` and `customer` roles
- Customer ticket creation with file upload support
- Employee ticket review dashboard
- Ticket-scoped chat history
- Source attachment display in the app UI
- Ticket close flow that writes a customer-facing email record
- Ticket deletion flow for SQLite-backed chat/file cleanup
- CRM support ticket autofill page in [`pages/crm_support_ticket_agent.html`](pages/crm_support_ticket_agent.html)

## Current UI Surfaces

- Login/signup screen: [`frontend/index.html`](frontend/index.html)
- Customer dashboard: [`pages/customer.html`](pages/customer.html)
- Employee dashboard: [`pages/employee.html`](pages/employee.html)
- CRM support agent page: [`pages/crm_support_ticket_agent.html`](pages/crm_support_ticket_agent.html)

## End-To-End Architecture

```text
Customer Files / Ticket Messages / Email History
                    |
                    v
                parser.py
                    |
                    v
                chunker.py
                    |
                    v
               embedder.py
                    |
                    v
        ChromaDB collections per customer
                    |
                    v
                  rag.py
                    |
                    v
       Flask API + SQLite app workflow layer
                    |
                    v
   Frontend login + customer page + employee page + CRM page
```

## Retrieval Pipeline

### 1. Parsing

[`parser.py`](parser.py) normalizes raw files into a structured representation that the rest of the pipeline can process consistently.

Supported inputs:

- PDF
- plain text
- markdown
- email (`.eml`)
- CSV
- XLSX
- PNG / JPG / JPEG / GIF / WEBP

The parser extracts:

- document text
- sections and block structure
- metadata such as filename and upload time
- email-related content
- spreadsheet table content
- OCR text from image-based inputs when applicable

LiteParse is used for PDF parsing and OCR-oriented extraction. An example asset is shown below.

![LiteParser demo](assets/liteparser-demo.webp)

### 2. Chunking

[`chunker.py`](chunker.py) splits parsed documents into smaller retrieval units.

Current defaults:

- chunk size: `512` tokens
- overlap: `50` tokens
- minimum chunk size: `50` tokens

Important chunk metadata includes:

- `customer_id`
- `source_file`
- `source_type`
- `document_date`
- `uploaded_at`
- `block_type`
- `heading_context`

That metadata is later used for:

- customer isolation
- source attribution
- date-aware ranking
- conflict handling
- UI source previews

### 3. Embedding And Storage

[`embedder.py`](embedder.py) embeds chunks using:

`all-MiniLM-L6-v2`

The vector store is:

`ChromaDB`

Each customer gets a separate Chroma collection. The collection name is derived from the customer id, which keeps retrieval isolated between customers.

Stored records include:

- deterministic chunk ids
- raw chunk text
- vector embeddings
- chunk metadata

### 4. Retrieval And Answer Generation

[`rag.py`](rag.py) handles:

- query embedding
- Chroma similarity search
- recency-based prioritization
- conflict heuristics
- prompt construction
- Groq completion calls
- structured answer packaging

For customer support chat, the system uses retrieval plus conversation history. For the CRM autofill assistant, it uses recent ticket context, email history, and retrieved customer document chunks.

## Source Priority And Conflict Handling

This project does not perform full symbolic contradiction reasoning. It uses pragmatic heuristics based on source metadata.

Current behavior:

- newer sources are prioritized over older ones
- dates are resolved from `document_date` and then `uploaded_at`
- recent emails can receive additional preference when ordering results
- if multiple sources disagree, the system favors the more recent source and exposes the conflict context

This logic lives in [`rag.py`](rag.py), mainly around recency prioritization and conflict detection.

Important limitation:

- this behavior is only as reliable as the date metadata extracted from the source files

## CRM Support Agent

The CRM support page in [`pages/crm_support_ticket_agent.html`](pages/crm_support_ticket_agent.html) is a structured support triage interface layered on top of the retrieval system.

It currently does the following:

- shows customer profile details
- shows customer-uploaded files
- shows email history sent to that customer
- lets an employee run an AI autofill flow for an open ticket
- fills:
  - category
  - issue summary
  - relevant context
  - reasoning
  - suggested resolution
- shows the retrieved source cards used by the agent
- submits by closing the selected ticket through the backend
- after close, the app records a resolution email in customer mail history

Important current behavior:

- the CRM autofill flow no longer depends on the shared company-policy collection
- it works from ticket history, email history, and customer document retrieval

## Ticketing And Email Workflow

The app includes a SQLite-backed ticket system implemented across [`backend/app.py`](backend/app.py) and [`backend/database.py`](backend/database.py).

### Customer-side workflow

- customers can sign up and log in
- customers can create tickets
- ticket creation supports message text and file uploads
- ticket conversations are stored in SQLite

### Employee-side workflow

- employees can browse customer tickets
- employees can ask questions in a ticket thread
- the backend runs retrieval-augmented responses
- responses can include source attachments for document inspection

### Ticket close behavior

Closing a ticket currently:

- updates the ticket status to `Closed`
- creates a customer mail entry in the SQLite mail table
- makes that email visible in customer and CRM email history views

The existing close route is:

- `POST /tickets/<ticket_id>/close`

### Delete chat behavior

Deleting a ticket chat currently removes:

- the ticket record
- ticket messages
- uploaded-file records for that ticket
- uploaded files from disk for that ticket

Important limitation:

- already embedded Chroma vectors for those documents are not deleted yet
- embeddings are still stored at customer scope, not ticket scope

## Project Structure

```text
assets/                README assets
backend/               Flask app, auth helpers, SQLite logic, runtime data
frontend/              Login/signup frontend assets
pages/                 Customer, employee, and CRM HTML pages
test_cases/            End-to-end sample pipeline
tests/unit/            Unit tests
tests/manual_outputs/  Manual parser output scripts
chunker.py             Chunking logic
embedder.py            Embedding and Chroma retrieval layer
parser.py              Multi-format parser
rag.py                 Retrieval orchestration and Groq integration
```

## Supported File Types

| File Type | Status | Notes |
| --- | --- | --- |
| PDF | Supported | Parsed with LiteParse |
| Text / Markdown | Supported | Sectioned into retrieval blocks |
| Email (`.eml`) | Supported | Email body plus metadata |
| Spreadsheet (`.csv`) | Supported | Parsed into normalized rows |
| Spreadsheet (`.xlsx`) | Supported | Parsed with `openpyxl` |
| Image (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`) | Supported | OCR/extraction path available |
| Outlook `.msg` | Not yet supported | Use `.eml` for now |
| Legacy `.xls` | Not yet supported | Use `.csv` or `.xlsx` |

## Why These Technical Choices Were Used

### `all-MiniLM-L6-v2`

This embedding model is a practical fit for an MVP because it is:

- lightweight enough for local development
- fast enough for repeated testing
- strong enough for general semantic retrieval
- easy to integrate through `sentence-transformers`

### ChromaDB

ChromaDB is used because it is:

- local and simple to run
- persistent on disk
- easy to inspect during development
- a good fit for document + metadata + embedding storage

### Groq

Groq is used for the answer-generation layer because it gives:

- low-latency inference
- a simple chat completion API
- a clean separation between local embeddings and hosted generation

## Setup

### 1. Install dependencies

This project uses `uv`.

```bash
uv sync
```

### 2. Configure environment variables

Create a root `.env` file with:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Optional:

```env
RAG_MODEL=llama-3.3-70b-versatile
```

`rag.py` loads `.env` automatically through `python-dotenv`.

### 3. Start the backend

```bash
uv run python backend/app.py
```

The backend listens on:

`http://localhost:5000`

### 4. Serve the frontend pages

```bash
uv run python -m http.server 5500
```

Open:

- Login app: `http://127.0.0.1:5500/frontend/index.html`
- Customer dashboard: `http://127.0.0.1:5500/pages/customer.html`
- Employee dashboard: `http://127.0.0.1:5500/pages/employee.html`
- CRM page: `http://127.0.0.1:5500/pages/crm_support_ticket_agent.html`

Important note:

- this is a static HTML/JS setup, not a Vite or Next.js dev server
- refresh the browser after frontend edits

## Running The Sample Retrieval Pipeline

```bash
uv run python test_cases/pipeline.py
```

This script demonstrates:

- parsing
- chunking
- embedding
- storing into Chroma
- asking interactive questions

## Running Evaluation

```bash
uv run python eval_rag.py
```

This evaluation flow:

- replays the sample questions listed in [`compare.md`](compare.md)
- uses the current `rag.py` behavior
- records raw results in `rag_eval_results.json`

Related files:

- [`compare.md`](compare.md)
- `rag_eval_results.json`

## Running Tests

### Unit tests

```bash
uv run python -m unittest tests.unit.test_chunker tests.unit.test_embedder
```

### Manual parser-output scripts

```bash
uv run python tests/manual_outputs/test_save_email_output.py
uv run python tests/manual_outputs/test_save_image_output.py
uv run python tests/manual_outputs/test_save_pdf_output.py
```

## API Overview

The backend in [`backend/app.py`](backend/app.py) includes routes for:

- signup and login
- profile lookup
- customer listing
- ticket listing and retrieval
- ticket message posting
- file access for uploaded ticket files
- customer mail history
- ticket close
- ticket delete
- CRM autofill

Representative routes:

- `POST /signup`
- `POST /login`
- `GET /customers`
- `GET /tickets`
- `GET /tickets/<ticket_id>/messages`
- `POST /tickets/<ticket_id>/messages`
- `GET /customer-files`
- `GET /mail`
- `POST /tickets/<ticket_id>/close`
- `POST /tickets/<ticket_id>/delete`
- `POST /crm/autofill`

## Current Status

### Working now

- multi-format retrieval pipeline
- customer-isolated vector search
- source-aware Groq responses
- customer and employee authentication
- ticket creation with file uploads
- ticket chat with retrieval-backed assistant responses
- email history tracking for resolved tickets
- employee dashboard with close/delete flows
- CRM support agent autofill flow

### Still limited

- `.msg` parsing is not implemented
- `.xls` parsing is not implemented
- conflict detection is heuristic, not semantic reasoning
- retrieval confidence tuning still needs calibration
- Chroma cleanup on ticket deletion is incomplete
- embeddings are still customer-scoped, not ticket-scoped
- frontend is static HTML/JS without hot reload tooling

## Known Limitations

- Date extraction quality strongly affects recency-based source prioritization.
- Deleting a ticket does not currently delete already-embedded document vectors for that ticket.
- CRM autofill is support-oriented and heuristic; it does not enforce a formal business-rules engine.
- Generated responses depend on Groq availability and valid API credentials.
- The project is optimized for local MVP iteration, not production deployment hardening.

## Roadmap

- add ticket-aware vector metadata for safe deletion
- improve conflict handling beyond date heuristics
- add broader automated coverage for `rag.py` and app flows
- support more enterprise document formats
- improve observability for retrieval quality and source usage
- refine CRM autofill outputs and action handling

