from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
from typing import Final, cast

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from auth import hash_password, verify_password
from chunker import chunk_documents
from database import (
    add_ticket_message,
    add_customer_mail,
    create_ticket,
    create_customer,
    delete_ticket,
    delete_company_file,
    create_employee,
    find_latest_uploaded_file,
    get_ticket,
    get_ticket_messages,
    get_company_file_by_id,
    get_uploaded_file_by_id,
    get_user_by_email,
    get_latest_user,
    get_user_by_username,
    initialize_database,
    list_all_customers,
    list_company_files,
    list_customer_mail,
    list_uploaded_files_for_ticket,
    list_uploaded_files_for_customer,
    list_all_tickets,
    list_tickets_for_customer,
    record_company_file,
    record_uploaded_file,
    update_ticket_status,
    find_latest_company_file,
)
from embedder import embed_and_store
from embedder import delete_customer_data
from parser import ParserError, parse_document
from rag import ask_with_history, generate_crm_autofill


VALID_ROLES: Final[set[str]] = {"employee", "customer"}
UPLOADS_DIR: Final[Path] = ROOT_DIR / "backend" / "uploads"
COMPANY_UPLOADS_DIR: Final[Path] = ROOT_DIR / "backend" / "company_uploads"
COMPANY_COLLECTION_ID: Final[str] = "__company_policy__"

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
CORS(
    app,
    resources={
        r"/signup": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:5500"],
        },
        r"/login": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:5500"],
        },
        r"/profile": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:5500"],
        },
        r"/customers": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:5500"],
        },
        r"/mail": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:5500"],
        },
        r"/customer-files": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:5500"],
        },
        r"/company-files": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:5500"],
        },
        r"/company-files/*": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:5500"],
        },
        r"/crm/autofill": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:5500"],
        },
        r"/tickets": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:5500"],
        },
        r"/tickets/*": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:5500"],
        },
    },
)


def _normalize_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _safe_filename(filename: str) -> str:
    name = Path(filename or "").name.strip()
    if not name:
        return "uploaded_file"
    return "".join(char if char.isalnum() or char in {".", "-", "_", " "} else "_" for char in name)


def _store_uploaded_file(customer_id: str, ticket_id: int, filename: str, file_bytes: bytes) -> Path:
    ticket_dir = UPLOADS_DIR / customer_id / str(ticket_id)
    ticket_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(filename)
    destination = ticket_dir / safe_name
    stem = destination.stem
    suffix = destination.suffix
    counter = 1
    while destination.exists():
        destination = ticket_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    destination.write_bytes(file_bytes)
    return destination


def _store_company_uploaded_file(filename: str, file_bytes: bytes) -> Path:
    COMPANY_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(filename)
    destination = COMPANY_UPLOADS_DIR / safe_name
    stem = destination.stem
    suffix = destination.suffix
    counter = 1
    while destination.exists():
        destination = COMPANY_UPLOADS_DIR / f"{stem}_{counter}{suffix}"
        counter += 1
    destination.write_bytes(file_bytes)
    return destination


def _build_source_attachment(source, customer_id: str, base_url: str) -> dict[str, object]:
    if getattr(source, "scope", "customer") == "company":
        uploaded_file = find_latest_company_file(source.source_file)
        file_id = cast(int, uploaded_file["id"]) if uploaded_file is not None else None
        file_type = cast(str, uploaded_file["file_type"]) if uploaded_file is not None else ""
        file_url = f"{base_url}/company-files/{file_id}" if file_id is not None else ""
    else:
        uploaded_file = find_latest_uploaded_file(customer_id, source.source_file)
        file_id = cast(int, uploaded_file["id"]) if uploaded_file is not None else None
        file_type = cast(str, uploaded_file["file_type"]) if uploaded_file is not None else ""
        file_url = f"{base_url}/uploaded-files/{file_id}" if file_id is not None else ""
    return {
        "kind": "source_reference",
        "scope": getattr(source, "scope", "customer"),
        "source_file": source.source_file,
        "page": source.page,
        "index": source.index,
        "chunk_id": source.chunk_id,
        "document_date": source.document_date,
        "uploaded_at": source.uploaded_at,
        "text_excerpt": source.text_excerpt,
        "heading_context": source.heading_context,
        "file_id": file_id,
        "file_url": file_url,
        "file_type": file_type,
    }


def _delete_uploaded_files_from_disk(ticket_id: int) -> None:
    for uploaded_file in list_uploaded_files_for_ticket(ticket_id):
        stored_path_value = cast(str, uploaded_file["stored_path"])
        if not stored_path_value:
            continue
        stored_path = Path(stored_path_value)
        if stored_path.is_file():
            stored_path.unlink(missing_ok=True)
        parent = stored_path.parent
        while parent != UPLOADS_DIR and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def _rebuild_company_policy_collection() -> None:
    delete_customer_data(COMPANY_COLLECTION_ID)
    parsed_docs = []
    for company_file in list_company_files():
        if cast(str, company_file["parse_status"]) != "parsed":
            continue
        stored_path = Path(cast(str, company_file["stored_path"]))
        if not stored_path.is_file():
            continue
        try:
            parsed_docs.append(
                parse_document(
                    stored_path,
                    filename=cast(str, company_file["filename"]),
                    content_type=cast(str, company_file["content_type"]),
                )
            )
        except ParserError:
            continue

    if not parsed_docs:
        return

    chunks = chunk_documents(parsed_docs, COMPANY_COLLECTION_ID)
    for chunk in chunks:
        chunk.metadata["scope"] = "company"
    embed_and_store(chunks)


def _serialize_company_file(company_file) -> dict[str, str | int]:
    return {
        "id": cast(int, company_file["id"]),
        "filename": cast(str, company_file["filename"]),
        "content_type": cast(str, company_file["content_type"]),
        "file_type": cast(str, company_file["file_type"]),
        "parse_status": cast(str, company_file["parse_status"]),
        "error_message": cast(str, company_file["error_message"]),
        "created_at": cast(str, company_file["created_at"]),
    }


def _serialize_uploaded_file(uploaded_file) -> dict[str, str | int]:
    return {
        "id": cast(int, uploaded_file["id"]),
        "ticket_id": cast(int, uploaded_file["ticket_id"]),
        "customer_id": cast(str, uploaded_file["customer_id"]),
        "filename": cast(str, uploaded_file["filename"]),
        "content_type": cast(str, uploaded_file["content_type"]),
        "file_type": cast(str, uploaded_file["file_type"]),
        "parse_status": cast(str, uploaded_file["parse_status"]),
        "error_message": cast(str, uploaded_file["error_message"]),
        "created_at": cast(str, uploaded_file["created_at"]),
    }


def _is_username_taken(username: str) -> bool:
    return (
        get_user_by_username(username, "employee") is not None
        or get_user_by_username(username, "customer") is not None
    )


def _is_email_taken(email: str) -> bool:
    return (
        get_user_by_email(email, "employee") is not None
        or get_user_by_email(email, "customer") is not None
    )


def _resolve_user(identifier: str, role: str):
    user = get_user_by_username(identifier, role)
    if user is None:
        user = get_user_by_email(identifier, role)
    return user


def _serialize_ticket(ticket) -> dict[str, str | int]:
    return {
        "id": cast(int, ticket["id"]),
        "customer_id": cast(str, ticket["customer_id"]),
        "customer_username": cast(str, ticket["customer_username"]),
        "customer_name": cast(str, ticket["customer_name"]),
        "subject": cast(str, ticket["subject"]),
        "status": cast(str, ticket["status"]),
        "last_message": cast(str, ticket["last_message"]),
        "created_at": cast(str, ticket["created_at"]),
        "updated_at": cast(str, ticket["updated_at"]),
    }


def _serialize_customer(customer) -> dict[str, str | int]:
    return {
        "customer_id": cast(str, customer["cust_id"]),
        "full_name": cast(str, customer["full_name"]),
        "username": cast(str, customer["username"]),
        "email": cast(str, customer["email"]),
        "created_at": cast(str, customer["created_at"]),
        "ticket_count": int(customer["ticket_count"]),
        "open_ticket_count": int(customer["open_ticket_count"]),
    }


def _serialize_message(message) -> dict[str, str | int | list[str]]:
    attachments_raw = cast(str, message["attachments_json"])
    try:
        attachments = json.loads(attachments_raw)
    except json.JSONDecodeError:
        attachments = []
    return {
        "id": cast(int, message["id"]),
        "ticket_id": cast(int, message["ticket_id"]),
        "role": cast(str, message["role"]),
        "sender_role": cast(str, message["sender_role"]),
        "content": cast(str, message["content"]),
        "attachments": attachments if isinstance(attachments, list) else [],
        "created_at": cast(str, message["created_at"]),
    }


def _serialize_customer_mail(mail) -> dict[str, str | int]:
    return {
        "id": cast(int, mail["id"]),
        "customer_id": cast(str, mail["customer_id"]),
        "ticket_id": cast(int, mail["ticket_id"]),
        "sender": cast(str, mail["sender"]),
        "subject": cast(str, mail["subject"]),
        "body": cast(str, mail["body"]),
        "created_at": cast(str, mail["created_at"]),
    }


def _ticket_subject_from_message(message: str, filenames: list[str]) -> str:
    normalized = message.strip()
    if normalized:
        return normalized[:120]
    if filenames:
        return f"Files uploaded: {', '.join(filenames[:3])}"[:120]
    return "New support ticket"


def _latest_customer_issue_for_ticket(ticket_id: int) -> str:
    messages = get_ticket_messages(ticket_id)
    for message in messages:
        if cast(str, message["sender_role"]) == "customer":
            content = cast(str, message["content"]).strip()
            if content:
                return content
    return ""


@app.post("/signup")
def signup():
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Invalid JSON body"}), 400

        full_name = _normalize_text(payload.get("full_name"))
        username = _normalize_text(payload.get("username"))
        email = _normalize_text(payload.get("email"))
        password = _normalize_text(payload.get("password"))
        role = _normalize_text(payload.get("role")).lower()
        entity_id = _normalize_text(payload.get("entity_id"))

        if not all([full_name, username, email, password, role, entity_id]):
            return (
                jsonify({"success": False, "message": "All fields are required"}),
                400,
            )

        if role not in VALID_ROLES:
            return jsonify({"success": False, "message": "Invalid role"}), 400

        if _is_username_taken(username):
            return jsonify({"success": False, "message": "Username already taken"}), 400

        if _is_email_taken(email):
            return jsonify({"success": False, "message": "Email already taken"}), 400

        password_hash = hash_password(password)

        if role == "customer":
            create_customer(entity_id, full_name, username, email, password_hash)
        else:
            create_employee(entity_id, full_name, username, email, password_hash)

        return jsonify({"success": True, "message": "Account created"}), 200
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.post("/login")
def login():
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Invalid JSON body"}), 400

        username = _normalize_text(payload.get("username"))
        password = _normalize_text(payload.get("password"))
        role = _normalize_text(payload.get("role")).lower()

        if not all([username, password, role]):
            return (
                jsonify({"success": False, "message": "All fields are required"}),
                400,
            )

        if role not in VALID_ROLES:
            return jsonify({"success": False, "message": "Invalid role"}), 400

        user = _resolve_user(username, role)
        if user is None:
            return jsonify({"success": False, "message": "User not found"}), 401

        stored_hash = cast(str, user["password_hash"])
        if not verify_password(password, stored_hash):
            return jsonify({"success": False, "message": "Incorrect password"}), 401

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Login successful",
                    "role": role,
                    "full_name": cast(str, user["full_name"]),
                    "username": cast(str, user["username"]),
                    "email": cast(str, user["email"]),
                }
            ),
            200,
        )
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.get("/profile")
def profile():
    try:
        username = _normalize_text(request.args.get("username"))
        role = _normalize_text(request.args.get("role")).lower()

        if role not in VALID_ROLES:
            return jsonify({"success": False, "message": "Invalid role"}), 400

        user = _resolve_user(username, role) if username else get_latest_user(role)
        if user is None:
            return jsonify({"success": False, "message": "User not found"}), 404

        entity_id_key = "emp_id" if role == "employee" else "cust_id"
        return (
            jsonify(
                {
                    "success": True,
                    "role": role,
                    "username": cast(str, user["username"]),
                    "full_name": cast(str, user["full_name"]),
                    "email": cast(str, user["email"]),
                    "entity_id": cast(str, user[entity_id_key]),
                }
            ),
            200,
        )
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.get("/customers")
def customers_route():
    try:
        return jsonify(
            {
                "success": True,
                "customers": [_serialize_customer(customer) for customer in list_all_customers()],
            }
        ), 200
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.get("/mail")
def customer_mail_route():
    try:
        customer_id = _normalize_text(request.args.get("customer_id"))
        if not customer_id:
            return jsonify({"success": False, "message": "Customer ID is required"}), 400

        mail_items = list_customer_mail(customer_id)
        return jsonify({"success": True, "mail": [_serialize_customer_mail(item) for item in mail_items]}), 200
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.get("/customer-files")
def customer_files_route():
    try:
        customer_id = _normalize_text(request.args.get("customer_id"))
        if not customer_id:
            return jsonify({"success": False, "message": "Customer ID is required"}), 400

        files = list_uploaded_files_for_customer(customer_id)
        return jsonify(
            {
                "success": True,
                "files": [_serialize_uploaded_file(item) for item in files],
            }
        ), 200
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.get("/company-files")
def company_files_route():
    try:
        return jsonify(
            {
                "success": True,
                "files": [_serialize_company_file(item) for item in list_company_files()],
            }
        ), 200
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.post("/company-files")
def company_files_upload_route():
    try:
        files = request.files.getlist("files")
        if not any(file.filename for file in files):
            return jsonify({"success": False, "message": "At least one file is required"}), 400

        parsed_docs = []
        uploaded_filenames: list[str] = []
        for file_storage in files:
            if not file_storage.filename:
                continue
            file_bytes = file_storage.read()
            stored_path = _store_company_uploaded_file(file_storage.filename, file_bytes)
            try:
                parsed = parse_document(
                    file_bytes,
                    filename=file_storage.filename,
                    content_type=file_storage.mimetype,
                )
                parsed_docs.append(parsed)
                uploaded_filenames.append(file_storage.filename)
                record_company_file(
                    filename=file_storage.filename,
                    stored_path=str(stored_path),
                    content_type=file_storage.mimetype or "",
                    file_type=parsed.file_type,
                    parse_status="parsed",
                )
            except ParserError as exc:
                record_company_file(
                    filename=file_storage.filename,
                    stored_path=str(stored_path),
                    content_type=file_storage.mimetype or "",
                    file_type="unknown",
                    parse_status="failed",
                    error_message=str(exc),
                )

        if parsed_docs:
            chunks = chunk_documents(parsed_docs, COMPANY_COLLECTION_ID)
            for chunk in chunks:
                chunk.metadata["scope"] = "company"
            embed_and_store(chunks)

        return jsonify({"success": True, "uploaded_files": uploaded_filenames}), 200
    except RuntimeError as error:
        return jsonify({"success": False, "message": str(error) or "Upload failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.get("/company-files/<int:file_id>")
def company_uploaded_file_route(file_id: int):
    try:
        company_file = get_company_file_by_id(file_id)
        if company_file is None:
            return jsonify({"success": False, "message": "File not found"}), 404

        stored_path = Path(cast(str, company_file["stored_path"]))
        if not stored_path.is_file():
            return jsonify({"success": False, "message": "Stored file not found"}), 404

        mimetype = cast(str, company_file["content_type"]) or None
        return send_file(stored_path, mimetype=mimetype, as_attachment=False)
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.post("/company-files/<int:file_id>/delete")
def company_file_delete_route(file_id: int):
    try:
        company_file = get_company_file_by_id(file_id)
        if company_file is None:
            return jsonify({"success": False, "message": "File not found"}), 404

        stored_path = Path(cast(str, company_file["stored_path"]))
        if stored_path.is_file():
            stored_path.unlink(missing_ok=True)

        deleted = delete_company_file(file_id)
        if not deleted:
            return jsonify({"success": False, "message": "File not found"}), 404

        _rebuild_company_policy_collection()
        return jsonify({"success": True}), 200
    except RuntimeError as error:
        return jsonify({"success": False, "message": str(error) or "Delete failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.post("/crm/autofill")
def crm_autofill_route():
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Invalid JSON body"}), 400

        customer_id = _normalize_text(payload.get("customer_id"))
        customer_name = _normalize_text(payload.get("customer_name"))
        email = _normalize_text(payload.get("email"))
        selected_ticket_id_raw = _normalize_text(payload.get("ticket_id"))
        if not customer_id:
            return jsonify({"success": False, "message": "Customer ID is required"}), 400

        customer_tickets = [
            ticket for ticket in list_all_tickets() if cast(str, ticket["customer_id"]) == customer_id
        ]
        customer_tickets.sort(
            key=lambda ticket: cast(str, ticket["updated_at"]) or cast(str, ticket["created_at"]),
            reverse=True,
        )
        open_customer_tickets = [
            ticket for ticket in customer_tickets if cast(str, ticket["status"]) != "Closed"
        ]

        selected_ticket = None
        if selected_ticket_id_raw:
            try:
                selected_ticket_id = int(selected_ticket_id_raw)
            except ValueError:
                return jsonify({"success": False, "message": "Ticket ID must be numeric"}), 400
            selected_ticket = next(
                (ticket for ticket in open_customer_tickets if cast(int, ticket["id"]) == selected_ticket_id),
                None,
            )
            if selected_ticket is None:
                return jsonify({"success": False, "message": "Selected open ticket not found"}), 404
        elif open_customer_tickets:
            selected_ticket = open_customer_tickets[0]

        recent_tickets: list[dict[str, object]] = []
        latest_customer_issue = ""
        selected_ticket_messages: list[dict[str, str | int]] = []
        prioritized_tickets = (
            [selected_ticket, *[ticket for ticket in customer_tickets if ticket != selected_ticket]]
            if selected_ticket is not None
            else customer_tickets
        )
        for ticket in prioritized_tickets[:5]:
            ticket_id = cast(int, ticket["id"])
            if selected_ticket is not None and ticket_id == cast(int, selected_ticket["id"]):
                selected_ticket_messages = [
                    _serialize_message(message)
                    for message in get_ticket_messages(ticket_id)[:8]
                ]
            issue_text = _latest_customer_issue_for_ticket(ticket_id)
            if not latest_customer_issue and issue_text:
                latest_customer_issue = issue_text
            recent_tickets.append(
                {
                    "ticket_id": ticket_id,
                    "subject": cast(str, ticket["subject"]),
                    "status": cast(str, ticket["status"]),
                    "created_at": cast(str, ticket["created_at"]),
                    "updated_at": cast(str, ticket["updated_at"]),
                    "customer_issue": issue_text,
                }
            )

        if not latest_customer_issue and recent_tickets:
            latest_customer_issue = str(recent_tickets[0].get("subject", "")).strip()
        if not latest_customer_issue:
            latest_customer_issue = "Customer requested support follow-up."

        mail_items = list_customer_mail(customer_id)
        recent_support_emails = [
            {
                "ticket_id": cast(int, mail["ticket_id"]),
                "subject": cast(str, mail["subject"]),
                "body": cast(str, mail["body"]),
                "created_at": cast(str, mail["created_at"]),
            }
            for mail in mail_items[:5]
        ]

        autofill = generate_crm_autofill(
            customer_name=customer_name or "Customer",
            customer_id=customer_id,
            email=email,
            latest_customer_issue=latest_customer_issue
            or " ".join(
                str(message.get("content", "")).strip()
                for message in selected_ticket_messages
                if str(message.get("sender_role", "")).strip() == "customer"
            ),
            open_ticket_count=len(open_customer_tickets),
            ticket_count=len(customer_tickets),
            recent_tickets=[
                *(
                    [
                        {
                            "ticket_id": cast(int, selected_ticket["id"]),
                            "subject": cast(str, selected_ticket["subject"]),
                            "status": cast(str, selected_ticket["status"]),
                            "created_at": cast(str, selected_ticket["created_at"]),
                            "updated_at": cast(str, selected_ticket["updated_at"]),
                            "customer_issue": latest_customer_issue,
                            "messages": selected_ticket_messages,
                        }
                    ]
                    if selected_ticket is not None
                    else []
                ),
                *[
                    ticket
                    for ticket in recent_tickets
                    if selected_ticket is None or cast(int, ticket["ticket_id"]) != cast(int, selected_ticket["id"])
                ],
            ],
            recent_support_emails=recent_support_emails,
        )
        base_url = request.host_url.rstrip("/")
        source_attachments = [
            _build_source_attachment(source, customer_id, base_url)
            for source in autofill.sources[:5]
        ]

        return jsonify(
            {
                "success": True,
                "autofill": {
                    "issue_summary": autofill.issue_summary,
                    "category": autofill.category,
                    "relevant_context": autofill.relevant_context,
                    "reasoning": autofill.reasoning,
                    "suggested_resolution": autofill.suggested_resolution,
                },
                "sources": source_attachments,
            }
        ), 200
    except RuntimeError as error:
        return jsonify({"success": False, "message": str(error) or "Autofill failed"}), 400
    except Exception as error:
        app.logger.exception("CRM autofill failed: %s", error)
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.post("/tickets/create")
def create_ticket_route():
    try:
        username = _normalize_text(request.form.get("username"))
        role = _normalize_text(request.form.get("role")).lower()
        message = _normalize_text(request.form.get("message"))
        files = request.files.getlist("files")

        if role != "customer":
            return jsonify({"success": False, "message": "Only customers can create tickets"}), 403
        if not username:
            return jsonify({"success": False, "message": "Username is required"}), 400
        if not message and not any(file.filename for file in files):
            return jsonify({"success": False, "message": "Message or files are required"}), 400

        user = _resolve_user(username, role)
        if user is None:
            return jsonify({"success": False, "message": "User not found"}), 404

        customer_id = cast(str, user["cust_id"])
        customer_username = cast(str, user["username"])
        customer_name = cast(str, user["full_name"])
        filenames = [file.filename for file in files if file.filename]
        ticket = create_ticket(
            customer_id=customer_id,
            customer_username=customer_username,
            customer_name=customer_name,
            subject=_ticket_subject_from_message(message, filenames),
        )

        parsed_docs = []
        uploaded_filenames: list[str] = []
        for file_storage in files:
            if not file_storage.filename:
                continue
            file_bytes = file_storage.read()
            stored_path = _store_uploaded_file(customer_id, cast(int, ticket["id"]), file_storage.filename, file_bytes)
            try:
                parsed = parse_document(
                    file_bytes,
                    filename=file_storage.filename,
                    content_type=file_storage.mimetype,
                )
                parsed_docs.append(parsed)
                uploaded_filenames.append(file_storage.filename)
                record_uploaded_file(
                    ticket_id=cast(int, ticket["id"]),
                    customer_id=customer_id,
                    filename=file_storage.filename,
                    stored_path=str(stored_path),
                    content_type=file_storage.mimetype or "",
                    file_type=parsed.file_type,
                    parse_status="parsed",
                )
            except ParserError as exc:
                record_uploaded_file(
                    ticket_id=cast(int, ticket["id"]),
                    customer_id=customer_id,
                    filename=file_storage.filename,
                    stored_path=str(stored_path),
                    content_type=file_storage.mimetype or "",
                    file_type="unknown",
                    parse_status="failed",
                    error_message=str(exc),
                )

        if parsed_docs:
            chunks = chunk_documents(parsed_docs, customer_id)
            embed_and_store(chunks)

        add_ticket_message(
            ticket_id=cast(int, ticket["id"]),
            role="user",
            sender_role="customer",
            content=message or "Uploaded files for support review.",
            attachments_json=json.dumps(uploaded_filenames),
        )
        refreshed_ticket = cast(object, get_ticket(cast(int, ticket["id"])))
        return jsonify({"success": True, "ticket": _serialize_ticket(refreshed_ticket)}), 200
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.get("/tickets")
def list_tickets_route():
    try:
        username = _normalize_text(request.args.get("username"))
        role = _normalize_text(request.args.get("role")).lower()
        if role not in VALID_ROLES:
            return jsonify({"success": False, "message": "Invalid role"}), 400

        tickets = (
            list_tickets_for_customer(username)
            if role == "customer" and username
            else list_all_tickets()
        )
        return jsonify({"success": True, "tickets": [_serialize_ticket(ticket) for ticket in tickets]}), 200
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.get("/tickets/<int:ticket_id>/messages")
def ticket_messages_route(ticket_id: int):
    try:
        ticket = get_ticket(ticket_id)
        if ticket is None:
            return jsonify({"success": False, "message": "Ticket not found"}), 404
        messages = get_ticket_messages(ticket_id)
        return jsonify(
            {
                "success": True,
                "ticket": _serialize_ticket(ticket),
                "messages": [_serialize_message(message) for message in messages],
            }
        ), 200
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.post("/tickets/<int:ticket_id>/message")
def ticket_message_create_route(ticket_id: int):
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "Invalid JSON body"}), 400

        username = _normalize_text(payload.get("username"))
        role = _normalize_text(payload.get("role")).lower()
        content = _normalize_text(payload.get("content"))
        if not all([username, role, content]):
            return jsonify({"success": False, "message": "Username, role, and content are required"}), 400

        ticket = get_ticket(ticket_id)
        if ticket is None:
            return jsonify({"success": False, "message": "Ticket not found"}), 404
        if cast(str, ticket["status"]) == "Closed":
            return jsonify({"success": False, "message": "Ticket is closed"}), 409

        add_ticket_message(
            ticket_id=ticket_id,
            role="user",
            sender_role="employee" if role == "employee" else "customer",
            content=content,
        )
        messages = get_ticket_messages(ticket_id)
        history = [
            {"role": cast(str, message["role"]), "content": cast(str, message["content"])}
            for message in messages[:-1]
            if cast(str, message["role"]) in {"user", "assistant"}
        ]
        rag_response = ask_with_history(
            customer_id=cast(str, ticket["customer_id"]),
            question=content,
            history=history,
        )
        base_url = request.host_url.rstrip("/")
        source_attachments = [
            _build_source_attachment(source, cast(str, ticket["customer_id"]), base_url)
            for source in rag_response.sources[:5]
        ]
        assistant_message = add_ticket_message(
            ticket_id=ticket_id,
            role="assistant",
            sender_role="assistant",
            content=rag_response.answer,
            attachments_json=json.dumps(source_attachments),
        )
        return jsonify(
            {
                "success": True,
                "assistant_message": _serialize_message(assistant_message),
                "sources_display": rag_response.sources_display,
            }
        ), 200
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.get("/uploaded-files/<int:file_id>")
def uploaded_file_route(file_id: int):
    try:
        uploaded_file = get_uploaded_file_by_id(file_id)
        if uploaded_file is None:
            return jsonify({"success": False, "message": "File not found"}), 404

        stored_path = Path(cast(str, uploaded_file["stored_path"]))
        if not stored_path.is_file():
            return jsonify({"success": False, "message": "Stored file not found"}), 404

        mimetype = cast(str, uploaded_file["content_type"]) or None
        return send_file(stored_path, mimetype=mimetype, as_attachment=False)
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.post("/tickets/<int:ticket_id>/close")
def close_ticket_route(ticket_id: int):
    try:
        ticket = get_ticket(ticket_id)
        if ticket is None:
            return jsonify({"success": False, "message": "Ticket not found"}), 404
        if cast(str, ticket["status"]) == "Closed":
            return jsonify({"success": False, "message": "Ticket is already closed"}), 409

        updated_ticket = update_ticket_status(ticket_id, "Closed")
        if updated_ticket is None:
            return jsonify({"success": False, "message": "Ticket not found"}), 404

        customer_name = cast(str, ticket["customer_name"])
        ticket_subject = cast(str, ticket["subject"])
        add_customer_mail(
            customer_id=cast(str, ticket["customer_id"]),
            ticket_id=ticket_id,
            subject=f"Ticket #{ticket_id} resolved",
            body=(
                f"Hello {customer_name},\n\n"
                f"Your support ticket #{ticket_id} has been resolved.\n\n"
                f"Issue: {ticket_subject}\n"
                f"Status: Closed\n\n"
                "If you still need help, please open a new ticket and our team will follow up.\n\n"
                "Best,\nKnowledgeAgent Support"
            ),
        )

        return jsonify({"success": True, "ticket": _serialize_ticket(updated_ticket)}), 200
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


@app.post("/tickets/<int:ticket_id>/delete")
def delete_ticket_route(ticket_id: int):
    try:
        ticket = get_ticket(ticket_id)
        if ticket is None:
            return jsonify({"success": False, "message": "Ticket not found"}), 404

        _delete_uploaded_files_from_disk(ticket_id)
        deleted = delete_ticket(ticket_id)
        if not deleted:
            return jsonify({"success": False, "message": "Ticket not found"}), 404

        return jsonify({"success": True}), 200
    except RuntimeError:
        return jsonify({"success": False, "message": "Database operation failed"}), 400
    except Exception:
        return jsonify({"success": False, "message": "Internal server error"}), 500


if __name__ == "__main__":
    initialize_database()
    app.run(host="0.0.0.0", port=5000, debug=False)
