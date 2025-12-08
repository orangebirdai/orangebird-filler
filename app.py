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
import docx                     # ← THIS LINE WAS MISSING
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

        # Make DOI/URLs blue & underlined
        if re.search(r"https?://|doi\.org", line):
            p = doc.add_paragraph()
            r = p.add_run(line)
            r.font.color.rgb = RGBColor(0, 0, 255)
            r.underline = True
        else:
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

    # 1. Worksheet
    prompt1 = f"""Complete the worksheet using {style} style. Answer every question in order.
Topic hint: {hint or 'none'}.

WORKSHEET:
\"\"\"{raw_text}\"\"\"

Return ONLY clean markdown."""

    resp1 = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt1}], temperature=0.2, max_tokens=8000)
    worksheet_md = resp1.choices[0].message.content
    w_path = f"uploads/COMP_{uuid.uuid4().hex[:8]}.docx"
    make_docx(worksheet_md, w_path)

    # 2. Get 8 real sources
    sources_prompt = f"""Return exactly 8 real, recent, peer-reviewed articles about this commodity.
For each return ONLY this JSON line:
{{"author":"Last, First","title":"...","journal":"...","year":"2024","volume":"","issue":"","pages":"","doi":"https://doi.org/...","url":"https://..."}} 

WORKSHEET:
\"\"\"{worksheet_md}\"\"\"

Return ONLY a valid JSON array."""

    sources_resp = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": sources_prompt}], temperature=0.3, max_tokens=4000)
    try:
        sources = json.loads(sources_resp.choices[0].message.content)
    except:
        sources = []

    # 3. Build correct bibliography + no double periods
    if style.upper() == "APA":
        bib_heading = "References"
    elif style.upper() == "CHICAGO":
        bib_heading = "Bibliography"
    else:
        bib_heading = "Works Cited"

    bib_lines = [f"{bib_heading}\n"]
    for s in sources[:8]:
        author = s.get("author", "Unknown Author")
        title = s.get("title", "Untitled")
        journal = s.get("journal", "")
        year = s.get("year", "n.d.")
        doi = s.get("doi", s.get("url", ""))

        entry = f"{author}. \"{title}.\" {journal}"
        if s.get("volume"): entry += f", vol. {s.get('volume')}"
        if s.get("issue"): entry += f", no. {s.get('issue')}"
        if s.get("pages"): entry += f", pp. {s.get('pages')}"
        if year != "n.d.": entry += f", {year}"
        if doi: entry += f", {doi}"
        entry += "."

        bib_lines.append(entry)
        bib_lines.append("")

    works_cited = "\n".join(bib_lines)

    # 4. Title + outline
    outline_prompt = f"""Create a strong title and 8–12 section outline for a {target_words}-word essay.
Return ONLY JSON: {{"title": "...", "outline": ["Section 1", ...]}}"""
    outline_resp = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": f"{outline_prompt}\n\nWORKSHEET:\n\"\"\"{worksheet_md}\"\"\""}], temperature=0.3, max_tokens=2000)
    try:
        plan = json.loads(outline_resp.choices[0].message.content)
    except:
        plan = {"title": "Commodity Analysis", "outline": [f"Part {i}" for i in range(1,11)]}

    # 5. Write sections
    full_essay = f"# {plan['title']}\n\n"
    current_words = 0

    for i, heading in enumerate(plan["outline"], 1):
        if current_words >= target_words:
            break
        remaining = target_words - current_words
        words_this_section = min(750, remaining + 150)

        section_prompt = f"""Write ONLY the body for section titled exactly:

{heading}

Target: ~{words_this_section} words.
55-year-old American senior analyst voice — first-person or “we/you”, contractions, casual markers, bursty sentences.
Use proper {style} in-text citations.
Never repeat previous content.

WORKSHEET:
\"\"\"{worksheet_md}\"\"\"

{bib_heading}:
{works_cited}

Return ONLY clean markdown body text — no heading."""

        resp = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": section_prompt}], temperature=0.5, max_tokens=3000)
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
