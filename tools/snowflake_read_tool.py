# tools/snowflake_read_tool.py
import os
import json
from typing import Optional
from datetime import datetime

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
    Env needed: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA, SNOWFLAKE_ROLE
    """
    account   = os.getenv("SNOWFLAKE_ACCOUNT")
    user      = os.getenv("SNOWFLAKE_USER")
    warehouse = os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
    database  = os.getenv("SNOWFLAKE_DATABASE", "HLEE3088_DB")
    schema    = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")
    role      = os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN")

    if not (account and user and warehouse and database and schema):
        raise RuntimeError("Missing one or more Snowflake env vars (ACCOUNT, USER, WAREHOUSE, DATABASE, SCHEMA).")

    private_key_pem = os.getenv("SNOWFLAKE_PRIVATE_KEY")
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
        # Accept both raw-PEM and base64-encoded PEM
        if "-----BEGIN PRIVATE KEY-----" in private_key_pem:
            key_bytes = private_key_pem.encode("utf-8")
        else:
            key_bytes = b64decode(private_key_pem)
        pkey = serialization.load_pem_private_key(
            key_bytes,
            password=(private_key_passphrase.encode("utf-8") if private_key_passphrase else None),
        )
        return snowflake.connector.connect(private_key=pkey, **conn_kwargs)

    if not password:
        raise RuntimeError("Provide SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY.")
    return snowflake.connector.connect(password=password, **conn_kwargs)


def _build_filters(source_type, context_tag, contains, since):
    clauses = []
    params  = []

    if source_type:
        clauses.append("SOURCE_TYPE = %s")
        params.append(source_type.strip())

    if context_tag:
        clauses.append("CONTEXT_TAG = %s")
        params.append(context_tag.strip())

    if contains:
        clauses.append("(TEXT_DATA ILIKE %s OR SUMMARY_DATA ILIKE %s)")
        like = f"%{contains.strip()}%"
        params.extend([like, like])

    if since:
        # Expect ISO-8601 string; let Snowflake parse
        clauses.append("INSERTED_AT >= %s")
        params.append(since.strip())

    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


@tool("snowflake_fetch_summaries", return_direct=False)
def snowflake_fetch_summaries(
    limit: int = 20,
    offset: int = 0,
    source_type: Optional[str] = None,
    context_tag: Optional[str] = None,
    contains: Optional[str] = None,
    since: Optional[str] = None,
) -> str:
    """
    Fetch rows from TEXT_SUMMARY with optional filters and pagination.
    Args:
      - limit: max rows to return (default 20)
      - offset: starting row offset (default 0)
      - source_type: filter by SOURCE_TYPE (e.g., 'OCR', 'Canvas', 'Voice', 'Agent')
      - context_tag: filter by CONTEXT_TAG (e.g., conversation id)
      - contains: substring search across TEXT_DATA and SUMMARY_DATA (case-insensitive)
      - since: ISO timestamp string (e.g., '2025-10-18T00:00:00') to filter INSERTED_AT >= since
    Returns JSON:
      {
        "ok": true,
        "limit": ...,
        "offset": ...,
        "total": <int or null>,
        "records": [
          {"ID": ..., "TEXT_DATA": "...", "SUMMARY_DATA":"...", "SOURCE_TYPE":"...", "CONTEXT_TAG":"...", "INSERTED_AT":"..."},
          ...
        ],
        "summary": "Readable one-line overview for screen readers"
      }
    """
    # sanity
    limit  = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    try:
        conn = _connect_snowflake()
        cur = conn.cursor()
        try:
            # Filters
            where_sql, params = _build_filters(source_type, context_tag, contains, since)

            # Total count (optional; useful for pagination UI)
            total = None
            try:
                cur.execute(f"SELECT COUNT(*) FROM TEXT_SUMMARY{where_sql}", params)
                total = cur.fetchone()[0]
            except Exception:
                total = None  # table might not exist yet

            # Main query
            sql = f"""
                SELECT ID, TEXT_DATA, SUMMARY_DATA, SOURCE_TYPE, CONTEXT_TAG,
                       TO_VARCHAR(INSERTED_AT, 'YYYY-MM-DD\"T\"HH24:MI:SS.FF3Z') AS INSERTED_AT
                FROM TEXT_SUMMARY
                {where_sql}
                ORDER BY INSERTED_AT DESC
                LIMIT %s OFFSET %s
            """
            cur.execute(sql, params + [limit, offset])
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]

            # Screen-reader friendly summary
            if not rows:
                sr = "No saved summaries matched your filters."
            else:
                head = rows[0]
                sr = (
                    f"Found {len(rows)} record(s)"
                    + (f" out of {total}" if total is not None else "")
                    + f". Latest source: {head.get('SOURCE_TYPE','Unknown')} at {head.get('INSERTED_AT','')}"
                    + (f", tag {head.get('CONTEXT_TAG')}" if head.get("CONTEXT_TAG") else "")
                    + "."
                )

            return json.dumps({
                "ok": True,
                "limit": limit,
                "offset": offset,
                "total": total,
                "records": rows,
                "summary": sr
            }, ensure_ascii=False)

        finally:
            cur.close()
            conn.close()

    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})