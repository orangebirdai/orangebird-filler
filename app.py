import os
import uuid
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from PyPDF2 import PdfReader
import io
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def extract_text(file_content: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(file_content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        doc = Document(io.BytesIO(file_content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

def create_proper_docx(content: str, title: str, path: str):
    doc = Document()
    doc.add_heading(title, 0)
    
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('# '):
            doc.add_heading(line[2:], level=1)
        elif line.startswith('## '):
            doc.add_heading(line[3:], level=2)
        elif line.startswith('- '):
            p = doc.add_paragraph(line[2:], style='List Bullet')
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif line:
            p = doc.add_paragraph(line)
            p.runs[0].font.size = Pt(11)
        else:
            doc.add_paragraph()  # blank line
    
    doc.save(path)

@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/complete")
async def complete_document(file: UploadFile = File(...), citation_style: str = Form("MLA"), topic_hint: str = Form("")):
    contents = await file.read()
    original_text = extract_text(contents, file.filename)
    
    prompt = f"""Complete this assignment perfectly in {citation_style} style. Topic hint: {topic_hint or 'general'}.

Document:
{original_text}

Return ONLY clean markdown with headings, bullets, and Works Cited at end."""
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=8000
    )
    completed_md = response.choices[0].message.content

    output_path = f"{UPLOAD_FOLDER}/COMPLETED_{uuid.uuid4().hex[:8]}.docx"
    create_proper_docx(completed_md, "Completed Worksheet", output_path)

    return {"file": output_path, "markdown": completed_md}

@app.post("/essay")
async def generate_essay(file: UploadFile = File(...), citation_style: str = Form("MLA")):
    contents = await file.read()
    original_text = extract_text(contents, file.filename)

    prompt = f"""Write a 1500-word academic essay based on this worksheet in {citation_style}.
Use formal tone, strong thesis, proper citations.

Document:
{original_text}

Return ONLY clean markdown."""
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=8000
    )
    essay_md = response.choices[0].message.content

    essay_path = f"{UPLOAD_FOLDER}/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    create_proper_docx(essay_md, "Full Essay", essay_path)

    return {"file": essay_path, "markdown": essay_md}

@app.get("/download/{filename:path}")
async def download(filename: str):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        return HTMLResponse("File expired — re-upload", status_code=404)
    return FileResponse(file_path, filename=os.path.basename(file_path))
