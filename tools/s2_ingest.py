# tools/s2_ingest.py
import os, json, re, requests
from typing import Optional
from langchain.tools import tool
from dotenv import load_dotenv
import snowflake.connector

load_dotenv()

S2_BASE = "https://api.semanticscholar.org/graph/v1"
S2_KEY  = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", "downloads")

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
    db = os.getenv("SNOWFLAKE_DATABASE", "HLEE3088_DB")
    sc = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")
    return f'{db}.{sc}.{table}'

def _headers():
    if not S2_KEY:
        raise RuntimeError("Missing SEMANTIC_SCHOLAR_API_KEY")
    return {"x-api-key": S2_KEY}

def _safe_filename(s: str) -> str:
    # slugify a bit; keep letters, digits, -_.; replace spaces with _
    s = s.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9._-]+", "", s)[:180] or "paper"

def _download_pdf(url: str, base_name: str) -> Optional[str]:
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    fn = _safe_filename(base_name) + ".pdf"
    path = os.path.join(DOWNLOADS_DIR, fn)
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "")
            if "pdf" not in ctype.lower():
                # Some OA links do 302 to PDF. If content-type is empty, still try.
                pass
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        f.write(chunk)
        return path
    except Exception:
        return None

@tool("s2_ingest_paper", return_direct=False)
def s2_ingest_paper(paper_id: str) -> str:
    """
    Fetch a paper from Semantic Scholar (by DOI/S2/arXiv/etc),
    upsert metadata into Snowflake, and download the openAccessPdf (if available).

    Returns JSON: { ok, paper_id, doi, title, saved_pdf?, snowflake_table }
    """
    fields = ",".join([
        "title","year","venue","authors","abstract",
        "referenceCount","citationCount","openAccessPdf","externalIds","url"
    ])

    # 1) Fetch from S2
    try:
        resp = requests.get(
            f"{S2_BASE}/paper/{paper_id}",
            headers=_headers(),
            params={"fields": fields},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return json.dumps({"ok": False, "error": f"s2_error: {e}"}, ensure_ascii=False)

    # Extract fields
    s2_id   = data.get("paperId") or ""
    title   = (data.get("title") or "").strip()
    year    = data.get("year")
    venue   = data.get("venue")
    authors = data.get("authors") or []
    abstract = data.get("abstract")
    refs    = data.get("referenceCount")
    cits    = data.get("citationCount")
    url     = data.get("url")
    ext     = data.get("externalIds") or {}
    doi     = ext.get("DOI")
    oa      = data.get("openAccessPdf") or {}
    oa_url  = oa.get("url")

    # 2) Download PDF (if possible)
    saved_pdf = None
    if oa_url:
        base_name = f"{doi or s2_id or _safe_filename(title) or 'paper'}"
        saved_pdf = _download_pdf(oa_url, base_name)

    # 3) Upsert into Snowflake
    tbl = _fq("S2_PAPERS")
    try:
        conn = _sf_conn()
        cur = conn.cursor()
        try:
            # Upsert by PAPER_ID if present, otherwise by DOI; if neither, just insert
            # Strategy: try update by PAPER_ID; if rowcount=0 and DOI exists, try by DOI; else insert.
            raw_json = json.dumps(data, ensure_ascii=False)

            # Try UPDATE by PAPER_ID
            rowcount = 0
            if s2_id:
                cur.execute(
                    f"""
                    UPDATE {tbl}
                    SET DOI=%s, TITLE=%s, YEAR=%s, VENUE=%s, AUTHORS=PARSE_JSON(%s),
                        ABSTRACT=%s, REFERENCE_COUNT=%s, CITATION_COUNT=%s,
                        OA_URL=%s, SOURCE_URL=%s, RAW_JSON=PARSE_JSON(%s)
                    WHERE PAPER_ID=%s
                    """,
                    (doi, title, year, venue, json.dumps(authors, ensure_ascii=False),
                     abstract, refs, cits, oa_url, url, raw_json, s2_id)
                )
                rowcount = cur.rowcount

            # If not updated and we have DOI, try UPDATE by DOI
            if rowcount == 0 and doi:
                cur.execute(
                    f"""
                    UPDATE {tbl}
                    SET PAPER_ID=%s, TITLE=%s, YEAR=%s, VENUE=%s, AUTHORS=PARSE_JSON(%s),
                        ABSTRACT=%s, REFERENCE_COUNT=%s, CITATION_COUNT=%s,
                        OA_URL=%s, SOURCE_URL=%s, RAW_JSON=PARSE_JSON(%s)
                    WHERE DOI=%s
                    """,
                    (s2_id, title, year, venue, json.dumps(authors, ensure_ascii=False),
                     abstract, refs, cits, oa_url, url, raw_json, doi)
                )
                rowcount = cur.rowcount

            # If no update happened, INSERT
            if rowcount == 0:
                cur.execute(
                    f"""
                    INSERT INTO {tbl} (
                      PAPER_ID, DOI, TITLE, YEAR, VENUE, AUTHORS, ABSTRACT,
                      REFERENCE_COUNT, CITATION_COUNT, OA_URL, SOURCE_URL, RAW_JSON
                    ) VALUES (%s,%s,%s,%s,%s,PARSE_JSON(%s),%s,%s,%s,%s,%s,PARSE_JSON(%s))
                    """,
                    (s2_id, doi, title, year, venue, json.dumps(authors, ensure_ascii=False),
                     abstract, refs, cits, oa_url, url, raw_json)
                )

            conn.commit()
        finally:
            try: cur.close()
            except: pass
            try: conn.close()
            except: pass
    except Exception as e:
        return json.dumps({"ok": False, "error": f"snowflake_error: {e}"}, ensure_ascii=False)

    return json.dumps({
        "ok": True,
        "paper_id": s2_id or paper_id,
        "doi": doi,
        "title": title,
        "saved_pdf": saved_pdf,
        "snowflake_table": tbl
    }, ensure_ascii=False)