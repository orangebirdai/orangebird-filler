import os
import uuid
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from docx import Document
from PyPDF2 import PdfReader
from grok import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
os.makedirs("uploads", exist_ok=True)

def extract_text(content: bytes, name: str) -> str:
    if name.lower().endswith(".pdf"):
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(content)).pages)
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

def make_docx(md: str, path: str):
    doc = Document()
    for line in md.split("\n"):
        line = line.rstrip()
        if line.startswith("# "): doc.add_heading(line[2:], 1)
        elif line.startswith("## "): doc.add_heading(line[3:], 2)
        elif line.startswith(("— ", "• ", "* ", "- ")): 
            doc.add_paragraph(line[2:].strip(), style="List Bullet")
        elif line:
            doc.add_paragraph(line)
        else:
            doc.add_paragraph("")
    doc.save(path)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/go")
async def go(file: UploadFile = File(...), style: str = Form("MLA"), hint: str = Form("")):
    text = extract_text(await file.read(), file.filename)

    # worksheet
    resp1 = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"Complete this assignment in {style}. Topic: {hint or 'none'}\n\n{text}\n\nReturn ONLY clean markdown with Works Cited."}],
        temperature=0.3, max_tokens=8000)
    w_path = f"uploads/COMP_{uuid.uuid4().hex[:8]}.docx"
    make_docx(resp1.choices[0].message.content, w_path)

    # essay
    resp2 = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"Write a 1500-word academic essay in {style} based on this worksheet:\n\n{text}\n\nReturn ONLY clean markdown."}],
        temperature=0.4, max_tokens=8000)
    e_path = f"uploads/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    make_docx(resp2.choices[0].message.content, e_path)

    return {"worksheet": w_path, "essay": e_path}

@app.get("/download/{path:path}")
async def dl(path: str):
    return FileResponse(path, filename=os.path.basename(path))
