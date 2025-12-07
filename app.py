import os
import uuid
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from docx import Document
from docx.shared import Pt, Inches
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

def markdown_to_docx(md: str, path: str):
    doc = Document()
    doc.add_heading("OrangeBird Filler – Completed Assignment", 0)

    for line in md.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        elif line.startswith("- ") or line.startswith("• "):
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(line[2:])
        elif line:
            doc.add_paragraph(line)
        else:
            if len(doc.paragraphs) > 0:
                doc.paragraphs[-1].add_run("\n")  # blank line
    doc.save(path)

@app.get("/")
async def home():
    return templates.TemplateResponse("index.html", {"request": {}})

@app.post("/complete")
async def complete(file: UploadFile = File(...), citation_style: str = Form("MLA"), topic_hint: str = Form("")):
    contents = await file.read()
    text = extract_text(contents, file.filename)

    prompt = f"""Complete this assignment perfectly in {citation_style} style. Topic hint: {topic_hint or 'none'}.

Document:
\"\"\"{text}\"\"\"

Return ONLY clean markdown with headings, bullets, and a Works Cited/References at the end."""
    
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=8000
    )
    md = resp.choices[0].message.content
    path = f"{UPLOAD_FOLDER}/COMPLETED_{uuid.uuid4().hex[:8]}.docx"
    markdown_to_docx(md, path)
    return {"file": path}

@app.post("/essay")
async def essay(file: UploadFile = File(...), citation_style: str = Form("MLA")):
    contents = await file.read()
    text = extract_text(contents, file.filename)

    prompt = f"""Write a 1500-word academic essay based on this worksheet in {citation_style}.
Use formal tone, strong thesis, and proper citations.

Document:
\"\"\"{text}\"\"\"

Return ONLY clean markdown."""
    
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=8000
    )
    md = resp.choices[0].message.content
    path = f"{UPLOAD_FOLDER}/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    markdown_to_docx(md, path)
    return {"file": path}

@app.get("/download/{filename:path}")
async def download(filename: str):
    return FileResponse(filename, filename=os.path.basename(filename))
