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


def _get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    try:
        with _get_connection() as connection:
            connection.execute(CUSTOMERS_SCHEMA)
            connection.execute(EMPLOYEES_SCHEMA)
            connection.commit()
    except sqlite3.Error as error:
        raise RuntimeError("Failed to initialize database") from error


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


initialize_database()
