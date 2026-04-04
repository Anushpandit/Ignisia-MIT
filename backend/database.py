from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "sme_app.db"


CUSTOMERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  cust_id     TEXT PRIMARY KEY,
  full_name   TEXT NOT NULL,
  username    TEXT UNIQUE NOT NULL,
  email       TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at  TEXT DEFAULT (datetime('now'))
);
"""


EMPLOYEES_SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
  emp_id      TEXT PRIMARY KEY,
  full_name   TEXT NOT NULL,
  username    TEXT UNIQUE NOT NULL,
  email       TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at  TEXT DEFAULT (datetime('now'))
);
"""


TICKETS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id       TEXT NOT NULL,
  customer_username TEXT NOT NULL,
  customer_name     TEXT NOT NULL,
  subject           TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'Open',
  last_message      TEXT NOT NULL DEFAULT '',
  created_at        TEXT DEFAULT (datetime('now')),
  updated_at        TEXT DEFAULT (datetime('now'))
);
"""


TICKET_MESSAGES_SCHEMA = """
CREATE TABLE IF NOT EXISTS ticket_messages (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id        INTEGER NOT NULL,
  role             TEXT NOT NULL,
  sender_role      TEXT NOT NULL,
  content          TEXT NOT NULL,
  attachments_json TEXT NOT NULL DEFAULT '[]',
  created_at       TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(ticket_id) REFERENCES tickets(id)
);
"""


UPLOADED_FILES_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploaded_files (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id     INTEGER NOT NULL,
  customer_id   TEXT NOT NULL,
  filename      TEXT NOT NULL,
  stored_path   TEXT NOT NULL DEFAULT '',
  content_type  TEXT NOT NULL DEFAULT '',
  file_type     TEXT NOT NULL DEFAULT '',
  parse_status  TEXT NOT NULL DEFAULT 'pending',
  error_message TEXT NOT NULL DEFAULT '',
  created_at    TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(ticket_id) REFERENCES tickets(id)
);
"""


CUSTOMER_MAIL_SCHEMA = """
CREATE TABLE IF NOT EXISTS customer_mail (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id TEXT NOT NULL,
  ticket_id   INTEGER NOT NULL,
  sender      TEXT NOT NULL DEFAULT 'support@knowledgeagent.ai',
  subject     TEXT NOT NULL,
  body        TEXT NOT NULL,
  created_at  TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(ticket_id) REFERENCES tickets(id)
);
"""


COMPANY_FILES_SCHEMA = """
CREATE TABLE IF NOT EXISTS company_files (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  filename      TEXT NOT NULL,
  stored_path   TEXT NOT NULL DEFAULT '',
  content_type  TEXT NOT NULL DEFAULT '',
  file_type     TEXT NOT NULL DEFAULT '',
  parse_status  TEXT NOT NULL DEFAULT 'pending',
  error_message TEXT NOT NULL DEFAULT '',
  created_at    TEXT DEFAULT (datetime('now'))
);
"""


SUPPORT_ACTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS support_actions (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id            INTEGER NOT NULL,
  customer_id          TEXT NOT NULL,
  customer_name        TEXT NOT NULL,
  customer_username    TEXT NOT NULL DEFAULT '',
  customer_email       TEXT NOT NULL DEFAULT '',
  category             TEXT NOT NULL DEFAULT '',
  issue_summary        TEXT NOT NULL DEFAULT '',
  relevant_context     TEXT NOT NULL DEFAULT '',
  reasoning            TEXT NOT NULL DEFAULT '',
  suggested_resolution TEXT NOT NULL DEFAULT '',
  actions_json         TEXT NOT NULL DEFAULT '[]',
  documents_json       TEXT NOT NULL DEFAULT '[]',
  references_json      TEXT NOT NULL DEFAULT '[]',
  created_at           TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(ticket_id) REFERENCES tickets(id)
);
"""


def _get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    try:
        with _get_connection() as connection:
            connection.execute(CUSTOMERS_SCHEMA)
            connection.execute(EMPLOYEES_SCHEMA)
            connection.execute(TICKETS_SCHEMA)
            connection.execute(TICKET_MESSAGES_SCHEMA)
            connection.execute(UPLOADED_FILES_SCHEMA)
            connection.execute(CUSTOMER_MAIL_SCHEMA)
            connection.execute(COMPANY_FILES_SCHEMA)
            connection.execute(SUPPORT_ACTIONS_SCHEMA)
            _ensure_column(connection, "uploaded_files", "stored_path", "TEXT NOT NULL DEFAULT ''")
            _ensure_column(connection, "company_files", "stored_path", "TEXT NOT NULL DEFAULT ''")
            connection.commit()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to initialize database") from error


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    existing_columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return
    connection.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    )


def create_customer(
    cust_id: str,
    full_name: str,
    username: str,
    email: str,
    password_hash: str,
) -> None:
    try:
        with _get_connection() as connection:
            connection.execute(
                """
                INSERT INTO customers (cust_id, full_name, username, email, password_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cust_id, full_name, username, email, password_hash),
            )
            connection.commit()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to create customer") from error


def create_employee(
    emp_id: str,
    full_name: str,
    username: str,
    email: str,
    password_hash: str,
) -> None:
    try:
        with _get_connection() as connection:
            connection.execute(
                """
                INSERT INTO employees (emp_id, full_name, username, email, password_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (emp_id, full_name, username, email, password_hash),
            )
            connection.commit()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to create employee") from error


def get_user_by_username(username: str, role: str) -> Optional[sqlite3.Row]:
    table_name = "employees" if role == "employee" else "customers"
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                f"SELECT * FROM {table_name} WHERE username = ?",
                (username,),
            )
            return cursor.fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to fetch user by username") from error


def get_user_by_email(email: str, role: str) -> Optional[sqlite3.Row]:
    table_name = "employees" if role == "employee" else "customers"
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                f"SELECT * FROM {table_name} WHERE email = ?",
                (email,),
            )
            return cursor.fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to fetch user by email") from error


def get_latest_user(role: str) -> Optional[sqlite3.Row]:
    table_name = "employees" if role == "employee" else "customers"
    id_column = "emp_id" if role == "employee" else "cust_id"
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                f"""
                SELECT *
                FROM {table_name}
                ORDER BY datetime(created_at) DESC, {id_column} DESC
                LIMIT 1
                """
            )
            return cursor.fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to fetch latest user") from error


def list_all_customers() -> list[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                SELECT
                    customers.*,
                    COALESCE(COUNT(tickets.id), 0) AS ticket_count,
                    COALESCE(SUM(CASE WHEN tickets.status != 'Closed' THEN 1 ELSE 0 END), 0) AS open_ticket_count
                FROM customers
                LEFT JOIN tickets
                    ON tickets.customer_username = customers.username
                GROUP BY customers.cust_id, customers.full_name, customers.username, customers.email, customers.password_hash, customers.created_at
                ORDER BY LOWER(customers.full_name) ASC, customers.cust_id ASC
                """
            )
            return cursor.fetchall()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to list customers") from error


def create_ticket(
    customer_id: str,
    customer_username: str,
    customer_name: str,
    subject: str,
    status: str = "Open",
) -> sqlite3.Row:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tickets (customer_id, customer_username, customer_name, subject, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (customer_id, customer_username, customer_name, subject, status),
            )
            ticket_id = cursor.lastrowid
            connection.commit()
            result = connection.execute(
                "SELECT * FROM tickets WHERE id = ?",
                (ticket_id,),
            ).fetchone()
            if result is None:
                raise RuntimeError("Created ticket could not be retrieved")
            return result
    except sqlite3.Error as error:
        raise RuntimeError("Failed to create ticket") from error


def add_ticket_message(
    ticket_id: int,
    role: str,
    sender_role: str,
    content: str,
    attachments_json: str = "[]",
) -> sqlite3.Row:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ticket_messages (ticket_id, role, sender_role, content, attachments_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ticket_id, role, sender_role, content, attachments_json),
            )
            connection.execute(
                """
                UPDATE tickets
                SET last_message = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (content[:400], ticket_id),
            )
            message_id = cursor.lastrowid
            connection.commit()
            result = connection.execute(
                "SELECT * FROM ticket_messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if result is None:
                raise RuntimeError("Created ticket message could not be retrieved")
            return result
    except sqlite3.Error as error:
        raise RuntimeError("Failed to add ticket message") from error


def record_uploaded_file(
    ticket_id: int,
    customer_id: str,
    filename: str,
    stored_path: str,
    content_type: str,
    file_type: str,
    parse_status: str,
    error_message: str = "",
) -> None:
    try:
        with _get_connection() as connection:
            connection.execute(
                """
                INSERT INTO uploaded_files (
                    ticket_id, customer_id, filename, stored_path, content_type, file_type, parse_status, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ticket_id, customer_id, filename, stored_path, content_type, file_type, parse_status, error_message),
            )
            connection.commit()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to record uploaded file") from error


def record_company_file(
    filename: str,
    stored_path: str,
    content_type: str,
    file_type: str,
    parse_status: str,
    error_message: str = "",
) -> None:
    try:
        with _get_connection() as connection:
            connection.execute(
                """
                INSERT INTO company_files (
                    filename, stored_path, content_type, file_type, parse_status, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (filename, stored_path, content_type, file_type, parse_status, error_message),
            )
            connection.commit()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to record company file") from error


def list_tickets_for_customer(customer_username: str) -> list[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                SELECT *
                FROM tickets
                WHERE customer_username = ?
                ORDER BY datetime(updated_at) DESC, id DESC
                """,
                (customer_username,),
            )
            return cursor.fetchall()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to list customer tickets") from error


def list_all_tickets() -> list[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                SELECT *
                FROM tickets
                ORDER BY datetime(updated_at) DESC, id DESC
                """
            )
            return cursor.fetchall()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to list tickets") from error


def get_ticket(ticket_id: int) -> Optional[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                "SELECT * FROM tickets WHERE id = ?",
                (ticket_id,),
            )
            return cursor.fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to get ticket") from error


def update_ticket_status(ticket_id: int, status: str) -> Optional[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            connection.execute(
                """
                UPDATE tickets
                SET status = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (status, ticket_id),
            )
            connection.commit()
            cursor = connection.execute(
                "SELECT * FROM tickets WHERE id = ?",
                (ticket_id,),
            )
            return cursor.fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to update ticket status") from error


def get_ticket_messages(ticket_id: int) -> list[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                SELECT *
                FROM ticket_messages
                WHERE ticket_id = ?
                ORDER BY datetime(created_at) ASC, id ASC
                """,
                (ticket_id,),
            )
            return cursor.fetchall()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to get ticket messages") from error


def get_uploaded_file_by_id(file_id: int) -> Optional[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                "SELECT * FROM uploaded_files WHERE id = ?",
                (file_id,),
            )
            return cursor.fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to get uploaded file") from error


def get_company_file_by_id(file_id: int) -> Optional[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                "SELECT * FROM company_files WHERE id = ?",
                (file_id,),
            )
            return cursor.fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to get company file") from error


def add_customer_mail(
    customer_id: str,
    ticket_id: int,
    subject: str,
    body: str,
    sender: str = "support@knowledgeagent.ai",
) -> sqlite3.Row:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO customer_mail (customer_id, ticket_id, sender, subject, body)
                VALUES (?, ?, ?, ?, ?)
                """,
                (customer_id, ticket_id, sender, subject, body),
            )
            mail_id = cursor.lastrowid
            connection.commit()
            result = connection.execute(
                "SELECT * FROM customer_mail WHERE id = ?",
                (mail_id,),
            ).fetchone()
            if result is None:
                raise RuntimeError("Created customer mail could not be retrieved")
            return result
    except sqlite3.Error as error:
        raise RuntimeError("Failed to add customer mail") from error


def list_customer_mail(customer_id: str) -> list[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                SELECT *
                FROM customer_mail
                WHERE customer_id = ?
                ORDER BY datetime(created_at) DESC, id DESC
                """,
                (customer_id,),
            )
            return cursor.fetchall()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to list customer mail") from error


def list_company_files() -> list[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                SELECT *
                FROM company_files
                ORDER BY datetime(created_at) DESC, id DESC
                """
            )
            return cursor.fetchall()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to list company files") from error


def delete_company_file(file_id: int) -> bool:
    try:
        with _get_connection() as connection:
            cursor = connection.execute("DELETE FROM company_files WHERE id = ?", (file_id,))
            connection.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as error:
        raise RuntimeError("Failed to delete company file") from error


def create_support_action(
    *,
    ticket_id: int,
    customer_id: str,
    customer_name: str,
    customer_username: str,
    customer_email: str,
    category: str,
    issue_summary: str,
    relevant_context: str,
    reasoning: str,
    suggested_resolution: str,
    actions_json: str = "[]",
    documents_json: str = "[]",
    references_json: str = "[]",
) -> sqlite3.Row:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO support_actions (
                    ticket_id,
                    customer_id,
                    customer_name,
                    customer_username,
                    customer_email,
                    category,
                    issue_summary,
                    relevant_context,
                    reasoning,
                    suggested_resolution,
                    actions_json,
                    documents_json,
                    references_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket_id,
                    customer_id,
                    customer_name,
                    customer_username,
                    customer_email,
                    category,
                    issue_summary,
                    relevant_context,
                    reasoning,
                    suggested_resolution,
                    actions_json,
                    documents_json,
                    references_json,
                ),
            )
            action_id = cursor.lastrowid
            connection.commit()
            result = connection.execute(
                "SELECT * FROM support_actions WHERE id = ?",
                (action_id,),
            ).fetchone()
            if result is None:
                raise RuntimeError("Created support action could not be retrieved")
            return result
    except sqlite3.Error as error:
        raise RuntimeError("Failed to create support action") from error


def list_support_actions() -> list[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                SELECT *
                FROM support_actions
                ORDER BY datetime(created_at) DESC, id DESC
                """
            )
            return cursor.fetchall()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to list support actions") from error


def find_latest_uploaded_file(customer_id: str, filename: str) -> Optional[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                SELECT *
                FROM uploaded_files
                WHERE customer_id = ? AND filename = ? AND parse_status = 'parsed'
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 1
                """,
                (customer_id, filename),
            )
            return cursor.fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to find uploaded file") from error


def find_latest_company_file(filename: str) -> Optional[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                SELECT *
                FROM company_files
                WHERE filename = ? AND parse_status = 'parsed'
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 1
                """,
                (filename,),
            )
            return cursor.fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to find company file") from error


def list_uploaded_files_for_ticket(ticket_id: int) -> list[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                SELECT *
                FROM uploaded_files
                WHERE ticket_id = ?
                ORDER BY id ASC
                """,
                (ticket_id,),
            )
            return cursor.fetchall()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to list uploaded files") from error


def list_uploaded_files_for_customer(customer_id: str) -> list[sqlite3.Row]:
    try:
        with _get_connection() as connection:
            cursor = connection.execute(
                """
                SELECT *
                FROM uploaded_files
                WHERE customer_id = ?
                ORDER BY datetime(created_at) DESC, id DESC
                """,
                (customer_id,),
            )
            return cursor.fetchall()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to list uploaded files for customer") from error


def delete_ticket(ticket_id: int) -> bool:
    try:
        with _get_connection() as connection:
            connection.execute("DELETE FROM support_actions WHERE ticket_id = ?", (ticket_id,))
            connection.execute("DELETE FROM customer_mail WHERE ticket_id = ?", (ticket_id,))
            connection.execute("DELETE FROM uploaded_files WHERE ticket_id = ?", (ticket_id,))
            connection.execute("DELETE FROM ticket_messages WHERE ticket_id = ?", (ticket_id,))
            ticket_cursor = connection.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
            connection.commit()
            return ticket_cursor.rowcount > 0
    except sqlite3.Error as error:
        raise RuntimeError("Failed to delete ticket") from error


initialize_database()
