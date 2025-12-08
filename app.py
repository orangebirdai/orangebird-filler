import os
import uuid
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
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

# ←←←←←←←←←←←←←←←←  THIS IS THE FIXED FUNCTION  ←←←←←←←←←←←←←←←←
def write_clean_docx(md: str, path: str, title: str):
    doc = Document()
    doc.add_heading(title, 0)

    for line in md.split("\n"):
        line = line.rstrip()
        if not line:
            doc.add_paragraph("")
            continue

        if line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        elif any(line.startswith(x) for x in ["- ", "• ", "* ", "1. ", "1) "]):
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(line[line.find(" ")+1:].strip())
        else:
            p = doc.add_paragraph(line)
            p.style = "Normal"

    # ←←← THIS LINE WAS MISSING BEFORE ←←←
    doc.save(path)
    # Force file sync so Render doesn’t truncate
    with open(path, 'ab'):  # append empty bytes to flush
        pass
# ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/process")
async def process(file: UploadFile = File(...), citation_style: str = Form("MLA"), topic_hint: str = Form("")):
    contents = await file.read()
    original_text = extract_text(contents, file.filename)

    # Worksheet
    prompt1 = f"""Complete this assignment perfectly in {citation_style}. Topic hint: {topic_hint or 'none'}.

Document:
\"\"\"{original_text}\"\"\"

Return ONLY clean markdown with headings, bullets, and a Works Cited section."""
    resp1 = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt1}], temperature=0.3, max_tokens=8000)
    md1 = resp1.choices[0].message.content
    worksheet_path = f"{UPLOAD_FOLDER}/COMPLETED_{uuid.uuid4().hex[:8]}.docx"
    write_clean_docx(md1, worksheet_path, "Completed Assignment")

    # Essay
    prompt2 = f"""Write a 1500-word academic essay based on this worksheet in {citation_style}.

Document:
\"\"\"{original_text}\"\"\"

Return ONLY clean markdown."""
    resp2 = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt2}], temperature=0.4, max_tokens=8000)
    md2 = resp2.choices[0].message.content
    essay_path = f"{UPLOAD_FOLDER}/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    write_clean_docx(md2, essay_path, "Full Essay")

    return {"worksheet": worksheet_path, "essay": essay_path}

@app.get("/download/{filename:path}")
async def download(filename: str):
    return FileResponse(filename, filename=os.path.basename(filename))
