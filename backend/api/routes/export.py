from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
import uuid
import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os

try:
    from weasyprint import HTML
except Exception:
    # BUG FIX: weasyprint's native GTK libs (gobject/pango) failing to load
    # raise OSError, not ImportError -- an ImportError-only guard let that
    # propagate and crash the entire app's module import chain at startup.
    HTML = None

router = APIRouter()

# BUG FIX (critical, injection): ExportRequest had no length/size limits, so
# any authenticated officer could submit an arbitrarily large query/answer or
# evidence list -- turned into a huge HTML document handed to the CPU/memory
# -heavy WeasyPrint renderer with no request-size or item-count guard.
class ExportRequest(BaseModel):
    query: str = Field(max_length=2000)
    answer: str = Field(max_length=20000)
    evidence: list[dict] = Field(default_factory=list, max_length=50)

_TEMPLATE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../templates'))
# BUG FIX (critical, injection): Environment() defaults to autoescape=False.
# query/answer/evidence are client-supplied (evidence is trusted wholesale
# from the request body, never re-derived server-side from a stored job
# result) and were rendered into report.html's {{ }} interpolations
# completely unescaped -- a crafted field could inject arbitrary HTML/CSS
# (e.g. <img>/<link> tags) into the document WeasyPrint then renders to PDF.
# select_autoescape HTML-escapes every interpolated value, neutralizing tag
# injection entirely.
_JINJA_ENV = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)

# BUG FIX (critical, SSRF / local file disclosure): WeasyPrint's default
# url_fetcher will follow http(s):// and file:// URLs it finds in the
# rendered HTML (e.g. an <img src="file:///etc/passwd"> or
# <img src="http://internal-host/..."> smuggled in via query/answer/evidence
# before the autoescape fix above, or via any future template change that
# renders a raw URL attribute). Report generation never legitimately needs to
# fetch anything external, so refuse every URL instead of trying to
# allowlist safe ones.
def _no_external_fetch(url):
    raise ValueError(f"External resource fetching is disabled for report generation (blocked: {url})")

@router.post("/api/export/pdf")
async def export_pdf(request: ExportRequest):
    if HTML is None:
        raise HTTPException(status_code=500, detail="WeasyPrint is not installed or configured correctly.")

    try:
        template = _JINJA_ENV.get_template('report.html')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template not found: {e}")

    # BUG FIX: template.render() was called outside any try/except, and
    # `evidence` is an unvalidated list[dict] -- a plausible client payload
    # (an item missing "data", or "data" not a dict) raised an uncaught
    # Jinja2 UndefinedError/AttributeError straight out of the endpoint as an
    # unhandled 500 instead of a clean 400.
    try:
        html_out = template.render(
            query=request.query,
            answer=request.answer,
            evidence=request.evidence,
            date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Malformed evidence payload: {e}")

    try:
        pdf_bytes = HTML(string=html_out, url_fetcher=_no_external_fetch).write_pdf()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF Generation failed: {e}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Intelligence_Report_{uuid.uuid4().hex[:8]}.pdf"}
    )
