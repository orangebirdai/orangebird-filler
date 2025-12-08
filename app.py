import os
import uuid
import io
import json
import asyncio
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
        temperature=0.2,
        max_tokens=8000
    )
    worksheet_md = resp1.choices[0].message.content
    w_path = f"uploads/COMP_{uuid.uuid4().hex[:8]}.docx"
    make_docx(worksheet_md, w_path)

    # 2. Build outline + Works Cited first
    outline_prompt = f"""Using ONLY the worksheet answers below, create:
1. A strong, original title for a {target_words}-word essay
2. A detailed outline with 8–12 main sections
3. A complete MLA Works Cited with exactly 8 real, verifiable peer-reviewed sources (include DOIs)

COMPLETED WORKSHEET:
\"\"\"{worksheet_md}\"\"\"

Return ONLY valid JSON:
{{"title": "...", "outline": ["Section 1", "Section 2", ...], "works_cited": "Full MLA text"}}"""

    outline_resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": outline_prompt}],
        temperature=0.3,
        max_tokens=4000
    )
    try:
        plan = json.loads(outline_resp.choices[0].message.content)
    except:
        plan = {
            "title": "Global Supply Chains and Commodity Risk",
            "outline": ["Introduction", "Production", "Major Markets", "Supply Chain Vulnerabilities", "Future Outlook"],
            "works_cited": "Works Cited\n(placeholder sources)"
        }

    # 3. Write essay section-by-section → no duplicates, exact word count
    sections = []
    words_per_section = max(150, target_words // len(plan["outline"]))

    for i, heading in enumerate(plan["outline"], 1):
        section_prompt = f"""Write section {i} titled "{heading}" of the essay titled "{plan['title']}".

Target length: ~{words_per_section} words (total essay must hit exactly {target_words} words).

Write like a 55-year-old American senior business analyst with 30+ years experience.
First-person or confident “we/you”, contractions, casual markers (“look,” “honestly,” “here’s the thing”), bursty sentences, start some with And/But/So/Because, one fragment every 300–400 words.
NO academic clichés. American English only.

Use ONLY facts from the worksheet and the sources below.

WORKSHEET ANSWERS:
\"\"\"{worksheet_md}\"\"\"

WORKS CITED:
{plan["works_cited"]}

Return ONLY the markdown for this section."""

        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": section_prompt}],
            temperature=0.65,
            max_tokens=4000
        )
        sections.append(f"## {heading}\n\n{resp.choices[0].message.content.strip()}")

    full_essay = f"# {plan['title']}\n\n" + "\n\n".join(sections) + f"\n\n{plan['works_cited']}"

    e_path = f"uploads/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    make_docx(full_essay, e_path)

    return {"worksheet": w_path, "essay": e_path}

@app.get("/download/{path:path}")
async def dl(path: str):
    return FileResponse(path, filename=os.path.basename(path))
