import os
import uuid
import io
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from docx import Document
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

def make_docx(md: str, path: str):
    doc = Document()
    title_added = False
    for line in md.split("\n"):
        line = line.rstrip()
        if not line:
            doc.add_paragraph("")
            continue
        if not title_added:
            p = doc.add_paragraph()
            p.add_run(line).bold = True
            p.style = "Title"
            title_added = True
            continue
        if any(line.lstrip().startswith(f"{i}.") for i in range(1, 100)) or "?" in line[:50]:
            p = doc.add_paragraph()
            p.add_run(line).bold = True
        else:
            doc.add_paragraph(line)
    doc.save(path)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/go")
async def go(file: UploadFile = File(...), style: str = Form("MLA"), hint: str = Form("")):
    raw_text = extract_text(await file.read(), file.filename)

    # 1. Perfect worksheet answers
    prompt1 = f"""You are completing the worksheet below.
Answer every question in order using the exact same numbering/format.
Do NOT add extra text. Use {style} citations. Topic hint: {hint or 'none'}.

WORKSHEET:
\"\"\"{raw_text}\"\"\"

Return ONLY clean markdown with question numbers followed by the answer."""

    resp1 = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt1}],
        temperature=0.2, max_tokens=8000)
    worksheet_md = resp1.choices[0].message.content
    w_path = f"uploads/COMP_{uuid.uuid4().hex[:8]}.docx"
    make_docx(worksheet_md, w_path)

    # 2. ESSAY — NOW GENERATES ITS OWN FITTING TITLE
    prompt2 = f"""You are a 55-year-old American senior business analyst with 30+ years of experience.
Write a 1200–1500 word essay based ONLY on the completed worksheet below.

First, invent a strong, original title that perfectly fits this commodity and its supply-chain story.
Then write the full essay in first-person or confident “we/you” style, full of contractions, casual markers (“look,” “honestly,” “here’s the thing”), bursty sentences, starting some with And/But/So/Because, one deliberate fragment every 300–400 words.
NO academic clichés. American English only.

Use at least 7 real, verifiable peer-reviewed sources with DOI links.
End with proper MLA Works Cited.

COMPLETED WORKSHEET:
\"\"\"{worksheet_md}\"\"\"

Return ONLY clean markdown. Start with the title as the very first line."""

    resp2 = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt2}],
        temperature=0.65,
        max_tokens=8000)
    essay_md = resp2.choices[0].message.content
    e_path = f"uploads/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    make_docx(essay_md, e_path)

    return {"worksheet": w_path, "essay": e_path}

@app.get("/download/{path:path}")
async def dl(path: str):
    return FileResponse(path, filename=os.path.basename(path))
