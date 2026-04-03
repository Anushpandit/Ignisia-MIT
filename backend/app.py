from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Final, cast

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask import Flask, jsonify, request
from flask_cors import CORS

from auth import hash_password, verify_password
from chunker import chunk_documents
from database import (
    add_ticket_message,
    create_ticket,
    create_customer,
    delete_ticket,
    create_employee,
    get_ticket,
    get_ticket_messages,
    get_user_by_email,
    get_latest_user,
    get_user_by_username,
    initialize_database,
    list_all_tickets,
    list_tickets_for_customer,
    record_uploaded_file,
    update_ticket_status,
)
from embedder import embed_and_store
from parser import ParserError, parse_document
from rag import ask_with_history


VALID_ROLES: Final[set[str]] = {"employee", "customer"}

app = Flask(__name__)
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


def _ticket_subject_from_message(message: str, filenames: list[str]) -> str:
    normalized = message.strip()
    if normalized:
        return normalized[:120]
    if filenames:
        return f"Files uploaded: {', '.join(filenames[:3])}"[:120]
    return "New support ticket"


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
                    content_type=file_storage.mimetype or "",
                    file_type=parsed.file_type,
                    parse_status="parsed",
                )
            except ParserError as exc:
                record_uploaded_file(
                    ticket_id=cast(int, ticket["id"]),
                    customer_id=customer_id,
                    filename=file_storage.filename,
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
        assistant_message = add_ticket_message(
            ticket_id=ticket_id,
            role="assistant",
            sender_role="assistant",
            content=rag_response.answer,
            attachments_json=json.dumps([source.source_file for source in rag_response.sources[:5]]),
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


@app.post("/tickets/<int:ticket_id>/close")
def close_ticket_route(ticket_id: int):
    try:
        ticket = get_ticket(ticket_id)
        if ticket is None:
            return jsonify({"success": False, "message": "Ticket not found"}), 404

        updated_ticket = update_ticket_status(ticket_id, "Closed")
        if updated_ticket is None:
            return jsonify({"success": False, "message": "Ticket not found"}), 404

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
