import os
import time

import psycopg2
from flask import Flask, jsonify, request
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "db"),
    "dbname": os.getenv("DB_NAME", "appdb"),
    "user": os.getenv("DB_USER", "appuser"),
    "password": os.getenv("DB_PASSWORD", "localdevpassword"),
    "connect_timeout": 3,
}

# @app.get("/health")
# def health():
#     # Process-level health only; does not prove DB connectivity.
#     return jsonify(status="ok"), 200


def connect_db():
    return psycopg2.connect(**DB_CONFIG)


def initialize_db():
    for attempt in range(1, 11):
        try:
            with connect_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS messages (
                            id SERIAL PRIMARY KEY,
                            content TEXT NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT NOW()
                        )
                    """)
            print("Database initialized", flush=True)
            return
        except psycopg2.OperationalError as exc:
            print(f"DB connection attempt {attempt}/10 failed: {exc}",
                  flush=True)
            time.sleep(2)

    raise RuntimeError("Could not initialize database after 10 attempts")


@app.get("/health")
def health():
    # Process-level health only; does not prove DB connectivity.
    return jsonify(status="ok"), 200


@app.get("/ready")
def ready():
    try:
        with connect_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return jsonify(status="ready", database="connected"), 200
    except psycopg2.Error:
        app.logger.exception("Readiness check failed")
        return jsonify(status="not_ready"), 503


@app.get("/api/messages")
def get_messages():
    try:
        with connect_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, content, created_at
                    FROM messages
                    ORDER BY id DESC
                    LIMIT 50
                """)
                rows = cur.fetchall()

        for row in rows:
            row["created_at"] = row["created_at"].isoformat()

        return jsonify(rows), 200
    except psycopg2.Error:
        app.logger.exception("Failed to fetch messages")
        return jsonify(error="Database query failed"), 503


@app.post("/api/messages")
def create_message():
    payload = request.get_json(silent=True) or {}
    content = payload.get("content", "")

    if not isinstance(content, str) or not content.strip():
        return jsonify(error="content must be a non-empty string"), 400

    try:
        with connect_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO messages (content) VALUES (%s) "
                    "RETURNING id, content, created_at",
                    (content.strip(),),
                )
                row = cur.fetchone()

        row["created_at"] = row["created_at"].isoformat()
        return jsonify(row), 201
    except psycopg2.Error:
        app.logger.exception("Failed to create message")
        return jsonify(error="Database query failed"), 503


initialize_db()
