from .mathpix_tool import mathpix_ocr
from .canvas_tool import canvas_assignments
from .s2_tool import s2_search
from .tts_tool import tts
from .gemini_summary_tool import gemini_summary  # <-- add this
from .auth_tool import auth_login
from .signup_tool import auth_signup
from .s2_ingest import s2_ingest_paper
TOOLS = [mathpix_ocr, canvas_assignments, s2_search, tts, gemini_summary, auth_login, auth_signup, s2_ingest_paper]