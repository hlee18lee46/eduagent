# tools/auth_tool.py
import os, json, bcrypt, snowflake.connector
from langchain.tools import tool
from dotenv import load_dotenv
load_dotenv()

def sf_conn():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
        role=os.getenv("SNOWFLAKE_ROLE"),
    )

@tool("auth_login", return_direct=False)
def auth_login(email: str, password: str, ip: str = None, user_agent: str = None) -> str:
    """Authenticate a user against Snowflake USERS table and return a simple session result."""
    email = (email or "").strip().lower()
    if not email or not password:
        return json.dumps({"ok": False, "error": "Missing email or password"})

    try:
        conn = sf_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT USER_ID, EMAIL, PASSWORD_HASH, ROLE
            FROM USERS WHERE LOWER(EMAIL)=LOWER(%s)
            LIMIT 1
        """, (email,))
        row = cur.fetchone()

        if not row:
            cur.execute("""
                INSERT INTO LOGIN_EVENTS (EMAIL, SUCCESS, ERROR_MSG)
                VALUES (%s, FALSE, 'not_found')
            """, (email,))
            conn.commit()
            return json.dumps({"ok": False, "error": "Invalid credentials"})

        user_id, db_email, pw_hash, role = row
        if not bcrypt.checkpw(password.encode(), pw_hash.encode()):
            cur.execute("""
                INSERT INTO LOGIN_EVENTS (USER_ID, EMAIL, SUCCESS, ERROR_MSG)
                VALUES (%s, %s, FALSE, 'invalid_password')
            """, (user_id, email))
            conn.commit()
            return json.dumps({"ok": False, "error": "Invalid credentials"})

        # success
        cur.execute("""
            INSERT INTO LOGIN_EVENTS (USER_ID, EMAIL, SUCCESS, IP_ADDRESS, USER_AGENT)
            VALUES (%s, %s, TRUE, %s, %s)
        """, (user_id, email, ip, user_agent))
        conn.commit()

        return json.dumps({
            "ok": True,
            "user": {"id": user_id, "email": db_email, "role": role}
        })

    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})

    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass