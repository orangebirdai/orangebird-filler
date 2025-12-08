import os
import uuid
import io
import json
import re
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from docx import Document
from docx.shared import Pt, RGBColor
from PyPDF2 import PdfReader
from groq import Groq
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

def count_words(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))

def make_docx(md: str, path: str):
    doc = Document()
    title_added = False
    current_heading = None
    for raw_line in md.split("\n"):
        line = raw_line.rstrip()
        if not line:
            doc.add_paragraph("")
            continue
        if not title_added and line.startswith("# "):
            p = doc.add_paragraph()
            p.add_run(line[2:]).bold = True
            p.style = "Title"
            title_added = True
            continue
        if line.startswith("## "):
            current_heading = line[3:].strip()
            p = doc.add_paragraph()
            p.add_run(current_heading).bold = True
            p.paragraph_format.space_after = Pt(6)
            continue
        if current_heading and line.strip() == current_heading:
            continue

        p = doc.add_paragraph()
        if re.search(r"https?://|doi\.org", line):
            parts = re.split(r'(https?://[^\s]+|doi\.org/[^\s]+)', line)
            for part in parts:
                if re.match(r"https?://|doi\.org", part):
                    run = p.add_run(part)
                    run.font.color.rgb = RGBColor(0, 0, 255)
                    run.underline = True
                else:
                    p.add_run(part)
        else:
            p.add_run(line)
    doc.save(path)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/go")
async def go(
    file: UploadFile = File(...),
    style: str = Form("MLA"),
    hint: str = Form(""),
    wordcount: str = Form("1500")
):
    raw_text = extract_text(await file.read(), file.filename)
    try:
        target_words = max(800, min(7000, int(wordcount)))
    except:
        target_words = 1500

    # 1. Worksheet
    prompt1 = f"""Complete the worksheet using {style}. Answer every question in order.
Topic hint: {hint or 'none'}.

WORKSHEET:
\"\"\"{raw_text}\"\"\"

Return ONLY clean markdown."""

    resp1 = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt1}], temperature=0.2, max_tokens=8000)
    worksheet_md = resp1.choices[0].message.content
    worksheet_file = f"uploads/COMP_{uuid.uuid4().hex[:10]}.docx"
    make_docx(worksheet_md, worksheet_file)

    # 2. Essay (keep your full section-by-section code here — unchanged)
    # ... [your full essay generation code from the last working version] ...
    # Just make sure you define `essay_file` at the end like this:
    essay_file = f"uploads/ESSAY_{uuid.uuid4().hex[:10]}.docx"
    make_docx(full_essay, essay_file)

    # 3. RETURN WORKING DOWNLOAD LINKS
    return HTMLResponse(f"""
    <html>
      <head><title>Done!</title></head>
      <body style="font-family:Arial; text-align:center; padding:50px; background:#f9f9f9;">
        <h1 style="color:#2c3e50;">Done!</h1>
        <p style="font-size:18px;">
          <a href="/download/{worksheet_file}" download style="color:#27ae60; font-weight:bold; text-decoration:none;">
            Download Completed Worksheet
          </a>
        </p>
        <p style="font-size:18px;">
          <a href="/download/{essay_file}" download style="color:#2980b9; font-weight:bold; text-decoration:none;">
            Download Essay ({target_words} words)
          </a>
        </p>
        <br><br>
        <a href="/" style="color:#7f8c8d;">← Do another one</a>
      </body>
    </html>
    """)

@app.get("/download/{filename:path}")
async def download(filename: str):
    file_path = f"uploads/{filename}"
    if not os.path.exists(file_path):
        return HTMLResponse("File not found or expired. Please generate again.", status_code=404)
    return FileResponse(file_path, filename=os.path.basename(filename))
