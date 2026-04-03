# Ignisia-MIT

Multi-Format Knowledge Retrieval Agent for SME Operations.

Ignisia-MIT is a retrieval-focused MVP for teams that need to search across fragmented business knowledge stored in PDFs, emails, spreadsheets, text files, and scanned images. The project now includes the full local retrieval pipeline:

- document parsing
- token-aware chunking
- embedding generation
- persistent vector storage with customer isolation
- retrieval-augmented answer generation with Groq
- source references and date-aware conflict handling
- customer and employee ticket workflows backed by SQLite
- ticket-scoped chat history in the app UI
- evaluation utilities for replaying RAG questions against the sample corpus

## Problem

SME teams often lose time searching through documents scattered across inboxes, reports, spreadsheets, and image-based records. Even when the information exists, it is difficult to:

- find the right file quickly
- know which file a fact came from
- compare older and newer documents when they disagree
- avoid answering from outdated documents

This project is built to turn those scattered files into a retrieval-ready knowledge base that can answer questions with source context.

## Current Status

### Working now

- Multi-format parsing in [`parser.py`](parser.py)
- Token-aware chunking in [`chunker.py`](chunker.py)
- Embedding generation and ChromaDB storage in [`embedder.py`](embedder.py)
- RAG answer generation with Groq in [`rag.py`](rag.py)
- Retrieval confidence gate in [`rag.py`](rag.py)
- Source attribution and conflict-aware answer formatting
- Flask auth backend in [`backend/`](backend/)
- Login/signup frontend in [`frontend/`](frontend/)
- Customer ticket creation and chat UI in [`pages/customer.html`](pages/customer.html)
- Employee dashboard UI in [`pages/employee.html`](pages/employee.html)
- Ticket message storage and uploaded-file records in SQLite
- Close-ticket and delete-chat flows in the employee dashboard
- Eval replay script in [`eval_rag.py`](eval_rag.py)
- Sample eval comparison notes in [`compare.md`](compare.md)
- Unit tests for chunking and embedding logic in [`tests/unit/`](tests/unit)
- Manual parsing/sample-output scripts in [`tests/manual_outputs/`](tests/manual_outputs)
- End-to-end sample pipeline in [`test_cases/pipeline.py`](test_cases/pipeline.py)

### Still limited / not finished

- `.msg` parsing is not supported yet
- legacy `.xls` parsing is not supported yet
- conflict detection is heuristic and date-driven, not full semantic contradiction detection
- Chroma embeddings are still stored per customer, not per ticket
- deleting a chat currently removes SQLite ticket/message/file records, but not already-embedded Chroma vectors for that ticket

## Architecture

### Retrieval Pipeline

```text
Customer Uploads Files
    |
    v
parser.py
  - Detects file type
  - Extracts text from PDFs, emails, spreadsheets, images, and text files
  - Produces a normalized ParsedDocument
    |
    v
chunker.py
  - Splits documents into retrieval chunks
  - Adds source-aware metadata
  - Preserves customer isolation with customer_id
    |
    v
embedder.py
  - Converts chunks into vector embeddings
  - Stores them in customer-specific ChromaDB collections
  - Retrieves semantically similar chunks for a query
    |
    v
rag.py
  - Reorders results by recency
  - Detects likely conflicts between sources
  - Builds a constrained prompt
  - Uses Groq to generate an answer with citations
```

### App Layer

```text
Frontend (Login / Signup / Employee + Customer pages)
    |
    v
Flask Backend
    |
    v
SQLite Ticket + User Store
    |
    v
ChromaDB + Groq-backed Retrieval
```

## LiteParser In Action

The parser uses LiteParse for PDF extraction and image OCR. The image below is included to visually show the LiteParse-based document parsing stage in the MVP workflow.

![LiteParser demo](assets/liteparser-demo.webp)

## Why These Technical Choices Were Made

### Embedding Model

This project uses the sentence-transformer model:

`all-MiniLM-L6-v2`

You can see this in [`embedder.py`](embedder.py):

```python
_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
```

#### Why this embedding model was used

This model is a practical choice for an MVP because it balances:

- good semantic search quality for short and medium text chunks
- relatively small size compared to larger embedding models
- fast local inference on a normal development machine
- broad community adoption and easy integration through `sentence-transformers`

For this project, those tradeoffs matter more than chasing the absolute best benchmark score. The retrieval system needs to:

- embed many chunks quickly
- support repeated local testing
- work without depending on an external embedding API

That makes `all-MiniLM-L6-v2` a strong fit for a hackathon/MVP setting.

#### What it is doing in this project

The model turns:

- each stored chunk
- and each incoming user question

into dense numeric vectors. ChromaDB then compares those vectors and returns the chunks whose meaning is closest to the user’s question.

So retrieval is based on semantic similarity, not exact keyword matching.

### Vector Database

This project uses:

`ChromaDB`

You can see this in [`embedder.py`](embedder.py):

```python
_chroma_client = chromadb.PersistentClient(path="./chroma_db")
```

#### Why ChromaDB was used

ChromaDB is a strong choice here because it is:

- simple to run locally
- persistent on disk
- easy to integrate into Python workflows
- well suited for semantic search prototypes and internal tools
- good for storing document text, metadata, ids, and embeddings together

For this project, the important requirement was not distributed scale. It was:

- fast local iteration
- easy inspection during development
- per-customer separation of knowledge
- ability to store metadata alongside each chunk

ChromaDB fits those needs well.

#### How ChromaDB is used here

Each customer gets a separate collection.

Collection naming is handled in [`embedder.py`](embedder.py):

```python
def _collection_name(customer_id: str) -> str:
    safe = customer_id.lower().strip().replace(" ", "_").replace("-", "_")
    return f"customer_{safe}"
```

That means:

- customer `001` becomes `customer_001`
- customer `Acme Corp` becomes `customer_acme_corp`

This is how retrieval stays customer-isolated.

When `rag.py` asks a question for one customer, the system only queries that customer’s Chroma collection.

### LLM / Answer Model

The answer generation layer uses:

- Groq API client
- default model: `llama-3.3-70b-versatile`

You can see this in [`rag.py`](rag.py):

```python
DEFAULT_MODEL = os.environ.get("RAG_MODEL", "llama-3.3-70b-versatile")
```

#### Why Groq was used

Groq is used here for the answer generation stage because the project needs:

- low-latency response generation
- a straightforward API
- support for modern chat-completions style prompting
- a clean way to test RAG behavior with source-aware prompts

The embedding stage is local, while the final answer generation is delegated to Groq.

This split is useful because:

- embeddings can be computed and stored locally
- answer quality can still benefit from a capable hosted LLM

## How The Pipeline Works

### 1. Parsing with `parser.py`

[`parser.py`](parser.py) reads raw input files and converts them into a normalized `ParsedDocument`.

Supported types include:

- PDF
- text / markdown
- email (`.eml`)
- spreadsheet (`.csv`, `.xlsx`)
- image (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`)

The parser extracts:

- full text
- section structure
- metadata such as filename and upload time
- spreadsheet tables
- email attachment information

For PDFs and images, LiteParse is used for extraction/OCR.

### 2. Chunking with `chunker.py`

[`chunker.py`](chunker.py) turns each parsed document into smaller retrieval units called chunks.

Important chunking settings:

- chunk size: `512` tokens
- overlap: `50` tokens
- minimum chunk size: `50` tokens

These values are defined in [`chunker.py`](chunker.py).

#### Why chunking is needed

Large documents are not searched as single giant blocks because:

- retrieval quality usually improves with smaller semantic units
- citations are easier to trace back
- answers become more specific
- vector search works better when chunks represent focused ideas

#### Metadata added to each chunk

Each chunk includes metadata such as:

- `customer_id`
- `source_file`
- `source_type`
- `document_date`
- `uploaded_at`
- `block_type`
- `heading_context`

This metadata is critical for:

- customer isolation
- source attribution
- conflict detection
- page/section display in the UI

### 3. Embedding and Storage with `embedder.py`

[`embedder.py`](embedder.py) takes chunks and stores them in ChromaDB.

The flow is:

1. group chunks by customer
2. create or open that customer’s Chroma collection
3. encode the chunk text into embedding vectors
4. upsert ids, embeddings, original text, and metadata into Chroma

The stored records include:

- deterministic chunk ids
- raw chunk text as documents
- dense vectors
- metadata

This makes retrieval explainable, because the system can return not just matching text, but also its source file and context.

### 4. Retrieval and Answer Generation with `rag.py`

[`rag.py`](rag.py) is the orchestration layer for answering questions.

When you call `ask(customer_id, question)`:

1. it validates the inputs
2. it queries Chroma for matching chunks using `query_collection(...)`
3. it reorders those results by recency
4. it detects likely conflicts across sources
5. it builds a constrained prompt for Groq
6. it returns a structured response with:
   - answer text
   - sources
   - conflict information
   - display-ready source summary

`rag.py` also now includes a retrieval confidence threshold:

- `RETRIEVAL_CONFIDENCE_THRESHOLD = 0.75`

If the best retrieved Chroma distance is above that threshold, the pipeline exits early and returns:

`I don't have enough information in your documents to answer this.`

This behavior is useful for reducing unsupported answers, but it is currently very aggressive for the sample evaluation set and likely needs recalibration.

## How Retrieval Works

Retrieval is semantic, not keyword-only.

When a question comes in:

1. the question is embedded using the same `all-MiniLM-L6-v2` model
2. ChromaDB searches for the nearest chunk vectors in that customer’s collection
3. the top `n_results` are returned

That means the system can still find relevant chunks even if the wording in the question is different from the wording in the document.

## Conflict Detection Strategy

This project includes a practical conflict-handling layer in [`rag.py`](rag.py).

It does not try to fully prove contradiction using symbolic reasoning. Instead, it uses source metadata and recency rules.

### Current logic

- retrieved chunks are grouped by source file
- the system resolves a date for each source using:
  - `document_date`
  - or `uploaded_at`
- the most recent source is treated as more trustworthy
- recent emails are given extra weight over older policy documents or spreadsheets

If multiple sources appear to disagree, the final prompt tells the LLM to:

- acknowledge the conflict explicitly
- identify which source is trusted
- explain why
- cite both the trusted and conflicting evidence

This is useful for real business workflows because many document disagreements are temporal rather than purely logical.

Example:

- old PDF says `14 days`
- newer email says `30 days`

The system should not silently pick one. It should explain the difference and prefer the newer source.

## RAG Prompt Design

The prompt in [`rag.py`](rag.py) is intentionally constrained.

It instructs the model to:

- answer only from the provided context
- avoid making things up
- cite sources as `[DOC-N]`
- mention dates
- explicitly handle conflicts
- explain why the trusted source was chosen

This improves reliability and makes debugging easier, because the generated answer is tied directly to retrieved source chunks.

## ChromaDB Folder Structure

The local vector store is persisted in:

[`chroma_db/`](chroma_db)

It generally contains:

- `chroma.sqlite3`
- one or more UUID-named index directories

In simple terms:

- the SQLite file stores metadata and collection state
- the UUID folders store the low-level vector index files used for nearest-neighbor search

This folder is ignored in git because it is generated runtime state, not source code.

## Supported File Types

| File Type | Status | Notes |
| --- | --- | --- |
| PDF | Supported | Parsed with LiteParse |
| Text / Markdown | Supported | Blank-line sectioning |
| Email (`.eml`) | Supported | Body extraction plus attachment metadata |
| Spreadsheet (`.csv`) | Supported | CSV rows normalized into structured tables |
| Spreadsheet (`.xlsx`) | Supported | Parsed with `openpyxl` |
| Image (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`) | Supported | OCR path available through LiteParse |
| Outlook `.msg` | Not yet supported | Use `.eml` for now |
| Legacy `.xls` | Not yet supported | Use `.csv` or `.xlsx` |

## Project Structure

```text
backend/               Flask auth API, SQLite auth storage, bcrypt helpers
frontend/              Login/signup frontend in TypeScript + compiled JS
pages/                 Customer and employee dashboard pages
examples/              Sample source documents
data/                  Sample parsed markdown and chunk outputs
assets/                README assets
tests/unit/            Unit tests for chunking and embedding
tests/manual_outputs/  Manual parsing / output-generation scripts
test_cases/            End-to-end sample pipeline for customer 001
parser.py              Multi-format parser
chunker.py             Chunking layer
embedder.py            Embedding + ChromaDB storage/retrieval
rag.py                 Groq-backed retrieval answer layer
```

## Example Outputs

### Parsed markdown outputs

- [`data/sample-report.md`](data/sample-report.md)
- [`data/sample-email.md`](data/sample-email.md)
- [`data/sample-ocr-image.md`](data/sample-ocr-image.md)

### Chunk outputs

- [`data/sample-report-chunks.json`](data/sample-report-chunks.json)
- [`data/sample-email-chunks.json`](data/sample-email-chunks.json)
- [`data/sample-ocr-image-chunks.json`](data/sample-ocr-image-chunks.json)

## Authentication Module

The project includes auth plus a ticketing workflow for customer and employee roles:

- signup and login UI in [`frontend/`](frontend/)
- Flask API in [`backend/app.py`](backend/app.py)
- SQLite persistence in [`backend/database.py`](backend/database.py)
- bcrypt password hashing in [`backend/auth.py`](backend/auth.py)
- customer ticket creation with file uploads
- employee ticket review with chat history
- ticket close action
- employee-side delete-chat action

Successful logins redirect users to role-specific pages in [`pages/`](pages/).

### Delete Chat Behavior

The employee dashboard includes a red `Delete chat` button next to `Close ticket`.

When used, it removes the selected ticket from SQLite by deleting:

- the `tickets` row
- all `ticket_messages` rows for that ticket
- all `uploaded_files` rows for that ticket

Important limitation:

- this does not yet remove any already-embedded document chunks from ChromaDB
- embeddings are stored by `customer_id`, not `ticket_id`
- because of that, the app does not yet know which stored vectors came from one exact ticket

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Add environment variables

Create a `.env` file in the project root with at least:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Optional:

```env
RAG_MODEL=llama-3.3-70b-versatile
```

`rag.py` loads `.env` automatically using `python-dotenv`.

### 3. Start the backend

```bash
uv run python backend/app.py
```

### 4. Serve the frontend

```bash
uv run python -m http.server 5500
```

Open:

```text
http://127.0.0.1:5500/frontend/index.html
```

## Running The Retrieval Pipeline

### Run the sample end-to-end pipeline

```bash
uv run python test_cases/pipeline.py
```

This script:

- creates a small mock corpus for customer `001`
- parses the documents
- chunks them
- embeds and stores them in ChromaDB
- lets you ask interactive questions
- shows retrieved chunks and the final Groq answer

## Running The Sample Evaluation

The repo now includes an eval replay script for the sample PDF:

```bash
uv run python eval_rag.py
```

This script:

- uses the existing Chroma collection for customer `rag-eval-sample-report`
- replays the 27 questions listed in [`compare.md`](compare.md)
- calls the current `rag.py`
- records best retrieval distances and whether the confidence gate fired
- writes structured results to [`rag_eval_results.json`](rag_eval_results.json)

Related files:

- [`compare.md`](compare.md): human-readable evaluation notes and before/after summaries
- [`rag_eval_results.json`](rag_eval_results.json): raw machine-readable replay output

## Running Tests

### Unit tests

```bash
uv run python -m unittest tests.unit.test_chunker tests.unit.test_embedder
```

### Manual parsing sample scripts

```bash
uv run python tests/manual_outputs/test_save_email_output.py
uv run python tests/manual_outputs/test_save_image_output.py
uv run python tests/manual_outputs/test_save_pdf_output.py
```

## Known Limitations

- conflict detection is based on recency heuristics, not full contradiction reasoning
- `.msg` email parsing is not implemented
- `.xls` spreadsheet parsing is not implemented
- duplicate chunk-id edge cases can still matter if chunk metadata is not unique enough
- the retrieval confidence threshold in [`rag.py`](rag.py) is not calibrated yet for the current Chroma distance distribution
- ticket deletion removes SQLite records but does not yet remove Chroma vectors for those uploaded documents
- vector storage is customer-scoped, so safe per-ticket embedding deletion needs additional metadata such as `ticket_id`

## Roadmap

- calibrate or redesign the retrieval confidence gate
- add ticket-aware embedding metadata so delete-chat can also remove Chroma vectors safely
- improve conflict detection beyond date heuristics
- expand test coverage for `rag.py`
- support additional enterprise document formats
- add observability around retrieval quality and source usage
