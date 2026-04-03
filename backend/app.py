from __future__ import annotations

from typing import Final, cast

from flask import Flask, jsonify, request
from flask_cors import CORS

from auth import hash_password, verify_password
from database import (
    create_customer,
    create_employee,
    get_user_by_email,
    get_latest_user,
    get_user_by_username,
    initialize_database,
)


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

        user = get_user_by_username(username, role)
        if user is None:
            user = get_user_by_email(username, role)
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

        user = get_user_by_username(username, role) if username else get_latest_user(role)
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


if __name__ == "__main__":
    initialize_database()
    app.run(host="0.0.0.0", port=5000, debug=False)
