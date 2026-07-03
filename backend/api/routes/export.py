from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import uuid
import datetime
from jinja2 import Environment, FileSystemLoader
import os

try:
    from weasyprint import HTML
except ImportError:
    HTML = None

router = APIRouter()

class ExportRequest(BaseModel):
    query: str
    answer: str
    evidence: list[dict] = []
    
_TEMPLATE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../templates'))
_JINJA_ENV = Environment(loader=FileSystemLoader(_TEMPLATE_DIR))
    
@router.post("/api/export/pdf")
async def export_pdf(request: ExportRequest):
    if HTML is None:
        raise HTTPException(status_code=500, detail="WeasyPrint is not installed or configured correctly.")
        
    try:
        template = _JINJA_ENV.get_template('report.html')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template not found: {e}")
        
    html_out = template.render(
        query=request.query,
        answer=request.answer,
        evidence=request.evidence,
        date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    
    try:
        pdf_bytes = HTML(string=html_out).write_pdf()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF Generation failed: {e}")
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Intelligence_Report_{uuid.uuid4().hex[:8]}.pdf"}
    )
