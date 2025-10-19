# tools/signup_tool.py
import os, json, bcrypt, snowflake.connector
from langchain.tools import tool
from dotenv import load_dotenv
load_dotenv()

def _sf_conn():
    return snowflake.connector.connect(
        account   = os.getenv("SNOWFLAKE_ACCOUNT"),
        user      = os.getenv("SNOWFLAKE_USER"),
        password  = os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse = os.getenv("SNOWFLAKE_WAREHOUSE"),
        database  = os.getenv("SNOWFLAKE_DATABASE", "HLEE3088_DB"),
        schema    = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
        role      = os.getenv("SNOWFLAKE_ROLE", "EDUAGENT_APP"),
        client_session_keep_alive=True,
    )

def _fq(table: str) -> str:
    # Fully-qualify with DB & schema from env
    db = os.getenv("SNOWFLAKE_DATABASE", "HLEE3088_DB")
    sc = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")
    return f'{db}.{sc}.{table}'

@tool("auth_signup", return_direct=False)
def auth_signup(email: str, password: str, role: str = "student") -> str:
    """
    Create a user row with bcrypt hash. No password policy enforced here.
    Uses fully qualified table names and only columns that exist.
    """
    email_norm = (email or "").strip().lower()
    if not email_norm or not password:
        return json.dumps({"ok": False, "error": "Missing email or password"})

    users_tbl = _fq("USERS")

    try:
        conn = _sf_conn()
        cur = conn.cursor()
        try:
            # Check duplicate
            cur.execute(
                f"SELECT USER_ID FROM {users_tbl} WHERE LOWER(EMAIL)=LOWER(%s) LIMIT 1",
                (email_norm,)
            )
            if cur.fetchone():
                return json.dumps({"ok": False, "error": "email_taken"})

            # Hash password
            pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")

            # Insert (only EMAIL, PASSWORD_HASH, ROLE — matches your table)
            cur.execute(
                f"INSERT INTO {users_tbl} (EMAIL, PASSWORD_HASH, ROLE) VALUES (%s, %s, %s)",
                (email_norm, pw_hash, role)
            )
            conn.commit()

            # Fetch created user
            cur.execute(
                f"SELECT USER_ID, EMAIL, ROLE FROM {users_tbl} WHERE LOWER(EMAIL)=LOWER(%s) LIMIT 1",
                (email_norm,)
            )
            row = cur.fetchone()
            if not row:
                return json.dumps({"ok": False, "error": "create_failed"})

            user_id, db_email, db_role = row
            return json.dumps({"ok": True, "user": {"id": user_id, "email": db_email, "role": db_role}})

        finally:
            try: cur.close()
            except: pass
            try: conn.close()
            except: pass

    except Exception as e:
        return json.dumps({"ok": False, "error": f"signup_error: {e}"})