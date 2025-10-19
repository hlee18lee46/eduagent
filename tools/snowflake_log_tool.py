# tools/snowflake_log_tool.py
import os
import json
from datetime import datetime
from typing import Optional

from langchain.tools import tool

# Snowflake connector
import snowflake.connector

# Optional: key-pair auth
from base64 import b64decode
from cryptography.hazmat.primitives import serialization


def _connect_snowflake():
    """
    Create a Snowflake connection using either:
      - Key-pair auth (SNOWFLAKE_PRIVATE_KEY [+ optional SNOWFLAKE_PRIVATE_KEY_PASSPHRASE])
      - OR password auth (SNOWFLAKE_PASSWORD)
    Required env:
      SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA, SNOWFLAKE_ROLE
    """
    account   = os.getenv("SNOWFLAKE_ACCOUNT")
    user      = os.getenv("SNOWFLAKE_USER")
    warehouse = os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
    database  = os.getenv("SNOWFLAKE_DATABASE", "HLEE3088_DB")
    schema    = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")
    role      = os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN")

    if not (account and user and warehouse and database and schema):
        raise RuntimeError("Missing one or more Snowflake env vars (ACCOUNT, USER, WAREHOUSE, DATABASE, SCHEMA).")

    private_key_pem = os.getenv("SNOWFLAKE_PRIVATE_KEY")  # PEM text (not base64) or base64-encoded blob you pasted
    private_key_passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
    password = os.getenv("SNOWFLAKE_PASSWORD")

    conn_kwargs = dict(
        account=account,
        user=user,
        warehouse=warehouse,
        database=database,
        schema=schema,
        role=role,
        application="EduAgent"
    )

    if private_key_pem:
        # Try to gracefully handle both raw-PEM and base64-blob cases
        key_bytes = None
        if "-----BEGIN PRIVATE KEY-----" in private_key_pem:
            key_bytes = private_key_pem.encode("utf-8")
        else:
            # assume base64-encoded PEM
            key_bytes = b64decode(private_key_pem)

        pkey = serialization.load_pem_private_key(
            key_bytes,
            password=(private_key_passphrase.encode("utf-8") if private_key_passphrase else None),
        )
        conn = snowflake.connector.connect(private_key=pkey, **conn_kwargs)
    else:
        if not password:
            raise RuntimeError("Provide SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY.")
        conn = snowflake.connector.connect(password=password, **conn_kwargs)

    return conn


def _ensure_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS TEXT_SUMMARY (
          ID INTEGER AUTOINCREMENT,
          TEXT_DATA STRING,
          SUMMARY_DATA STRING,
          SOURCE_TYPE STRING,
          CONTEXT_TAG STRING,
          INSERTED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        );
    """)


@tool("snowflake_log_summary", return_direct=False)
def snowflake_log_summary(
    text_data: str,
    summary_data: str,
    source_type: Optional[str] = None,
    context_tag: Optional[str] = None,
) -> str:
    """
    Insert raw text + summary into Snowflake TEXT_SUMMARY table.
    Arguments:
      - text_data:     original text (OCR, Canvas, etc.)
      - summary_data:  the generated summary
      - source_type:   e.g. "OCR", "Canvas", "Voice", "SemanticScholar"
      - context_tag:   optional conversation id / label

    Returns JSON: { "ok": true, "row_id": <int> } or { "ok": false, "error": <str> }
    """
    # Light sanitization / truncation (adjust as needed)
    text_data = (text_data or "").strip()
    summary_data = (summary_data or "").strip()
    source_type = (source_type or "Agent").strip()[:64]
    context_tag = (context_tag or "").strip()[:128]

    try:
        conn = _connect_snowflake()
        cur = conn.cursor()
        try:
            _ensure_table(cur)

            # Parameterized insert
            cur.execute(
                """
                INSERT INTO TEXT_SUMMARY (TEXT_DATA, SUMMARY_DATA, SOURCE_TYPE, CONTEXT_TAG)
                VALUES (%s, %s, %s, %s)
                """,
                (text_data, summary_data, source_type, context_tag)
            )

            # Snowflake lets us fetch the last identity with IDENT_CURRENT in same session;
            # simpler: return rowcount and UTC timestamp (or get MAX(ID) if needed).
            inserted = cur.rowcount
            conn.commit()

            return json.dumps({
                "ok": True,
                "rowcount": inserted,
                "source_type": source_type,
                "context_tag": context_tag
            })
        finally:
            cur.close()
            conn.close()

    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})