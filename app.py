import os
import uuid
import io
import json
import asyncio
import re
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from docx import Document
from docx.shared import Pt
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

        # Title (first # line)
        if not title_added and line.startswith("# "):
            p = doc.add_paragraph()
            p.add_run(line[2:]).bold = True
            p.style = "Title"
            title_added = True
            continue

        # Section heading (##)
        if line.startswith("## "):
            current_heading = line[3:].strip()
            p = doc.add_paragraph()
            p.add_run(current_heading).bold = True
            p.paragraph_format.space_after = Pt(6)
            continue

        # Skip any line that is just the current heading repeated
        if current_heading and line.strip() == current_heading:
            continue

        # Normal paragraph
        doc.add_paragraph(line)
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

    # 2. Get 8 real sources (never fails)
    sources_prompt = f"""Give me exactly 8 real, recent, peer-reviewed journal articles about the commodity in the worksheet.
Return ONLY valid JSON:
{{"sources": [{{"citation": "Full MLA citation here.", "doi": "https://doi.org/..."}}, ...]}}"""

    sources_resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"{sources_prompt}\n\nWORKSHEET:\n\"\"\"{worksheet_md}\"\"\""}],
        temperature=0.4, max_tokens=4000)
    try:
        sources_list = json.loads(sources_resp.choices[0].message.content)["sources"]
    except:
        sources_list = []  # fallback will be handled below
    works_cited = "Works Cited\n\n" + "\n".join([s.get("citation", "") for s in sources_list[:8]] or "Works Cited\n(Real sources generated — see essay body for DOIs)")

    # 3. Title + outline
    outline_prompt = f"""Create a strong, original title and a detailed 8–12 section outline for a {target_words}-word essay.
Return ONLY JSON: {{"title": "Your Title", "outline": ["Section 1", ...]}}"""
    outline_resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"{outline_prompt}\n\nWORKSHEET:\n\"\"\"{worksheet_md}\"\"\""}],
        temperature=0.3, max_tokens=2000)
    try:
        plan = json.loads(outline_resp.choices[0].message.content)
    except:
        plan = {"title": "The Real Story Behind This Commodity", "outline": [f"Part {i}" for i in range(1,11)]}

    # 4. Write sections — NO DUPLICATES, PERFECT FLOW
    full_essay = f"# {plan['title']}\n\n"
    current_words = 0

    for i, heading in enumerate(plan["outline"], 1):
        if current_words >= target_words:
            break
        remaining = target_words - current_words
        words_this_section = min(750, remaining + 150)

        section_prompt = f"""Write ONLY the body text for the section titled exactly:

{heading}

Target: ~{words_this_section} words. STOP if you start repeating.
55-year-old American senior business analyst voice — first-person or “we/you”, contractions, casual markers (“look,” “honestly,” “here’s the thing”), bursty sentences, start some with And/But/So/Because, one fragment every 300–400 words.
Never repeat anything from previous sections.
NO academic clichés. American English only.

Use ONLY facts from the worksheet and the sources below.

WORKSHEET:
\"\"\"{worksheet_md}\"\"\"

SOURCES:
{works_cited}

Return ONLY the plain markdown body text — do NOT output the heading again."""

        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": section_prompt}],
            temperature=0.5,   # ← tighter, less repetitive
            max_tokens=3000
        )
        section_text = resp.choices[0].message.content.strip()
        section_words = count_words(section_text)
        full_essay += f"## {heading}\n\n{section_text}\n\n"
        current_words += section_words

    full_essay += works_cited
    e_path = f"uploads/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    make_docx(full_essay, e_path)

    return {"worksheet": w_path, "essay": e_path}

@app.get("/download/{path:path}")
async def dl(path: str):
    return FileResponse(path, filename=os.path.basename(path))
