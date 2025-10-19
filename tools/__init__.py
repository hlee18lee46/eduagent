from .mathpix_tool import mathpix_ocr
from .canvas_tool import canvas_assignments
from .s2_tool import s2_search
from .tts_tool import tts
from .gemini_summary_tool import gemini_summary  # <-- add this
from .auth_tool import auth_login
from .signup_tool import auth_signup
from .s2_ingest import s2_ingest_paper
from .llvm_mca_tool import llvm_mca_report
from .canvas_course_tool import canvas_courses
from .snowflake_log_tool import snowflake_log_summary   # <-- NEW
from .snowflake_read_tool import snowflake_fetch_summaries   # <-- NEW

TOOLS = [mathpix_ocr, canvas_assignments, s2_search, tts, gemini_summary, auth_login, auth_signup, s2_ingest_paper, llvm_mca_report, canvas_courses, snowflake_log_summary, snowflake_fetch_summaries]