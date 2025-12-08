import os
import uuid
import io
import json
import asyncio
import re                  # ← THIS LINE WAS MISSING
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

def count_words(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))

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
    prompt1 = f"""You are completing the worksheet below.
Answer every question in order using the exact same numbering/format.
Do NOT add extra text. Use {style} citations. Topic hint: {hint or 'none'}.

WORKSHEET:
\"\"\"{raw_text}\"\"\"

Return ONLY clean markdown with question numbers followed by the answer."""

    resp1 = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt1}],
        temperature=0.2,
        max_tokens=8000
    )
    worksheet_md = resp1.choices[0].message.content
    w_path = f"uploads/COMP_{uuid.uuid4().hex[:8]}.docx"
    make_docx(worksheet_md, w_path)

    # 2. Outline + sources
    outline_prompt = f"""Using ONLY the worksheet answers below, create:
1. A strong, original title for a {target_words}-word essay
2. An outline with 8–12 sections
3. MLA Works Cited with exactly 8 real, verifiable peer-reviewed sources (include DOIs)

Return ONLY valid JSON:
{{"title": "...", "outline": ["Section 1", ...], "works_cited": "Full MLA text"}}"""

    outline_resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"{outline_prompt}\n\nWORKSHEET:\n\"\"\"{worksheet_md}\"\"\""}],
        temperature=0.3,
        max_tokens=4000
    )
    try:
        plan = json.loads(outline_resp.choices[0].message.content)
    except:
        plan = {"title": "Commodity Analysis", "outline": [f"Section {i}" for i in range(1,11)], 
                "works_cited": "Works Cited\n(placeholder)"}

    # 3. Section-by-section essay with exact word control
    full_essay = f"# {plan['title']}\n\n"
    current_words = 0

    for i, heading in enumerate(plan["outline"], 1):
        if current_words >= target_words:
            break
        remaining = target_words - current_words
        words_this_section = min(800, remaining + 200)

        section_prompt = f"""Write section titled "{heading}" of the essay "{plan['title']}".

Target: ~{words_this_section} words (stop early if total would exceed {target_words}).

55-year-old American senior analyst voice, first-person or “we/you”, contractions, casual markers, bursty sentences, one fragment every 300–400 words.
NO academic clichés. American English only.

Use ONLY facts from the worksheet and sources below.

WORKSHEET:
\"\"\"{worksheet_md}\"\"\"

SOURCES:
{plan["works_cited"]}

Return ONLY the markdown for this section."""

        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": section_prompt}],
            temperature=0.65,
            max_tokens=3000
        )
        section_text = resp.choices[0].message.content.strip()
        section_words = count_words(section_text)

        full_essay += f"## {heading}\n\n{section_text}\n\n"
        current_words += section_words

    full_essay += plan["works_cited"]
    e_path = f"uploads/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    make_docx(full_essay, e_path)

    return {"worksheet": w_path, "essay": e_path}

@app.get("/download/{path:path}")
async def dl(path: str):
    return FileResponse(path, filename=os.path.basename(path))
