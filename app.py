import os
import uuid
import io
import json
import re
from fastapi import asyncio
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

# (extract_text and make_docx stay exactly the same as your current ones)

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

    # 1. Worksheet — unchanged, perfect as-is
    prompt1 = f"""You are completing the worksheet below.
Answer every question in order using the exact same numbering/format.
Do NOT add extra text. Use {style} citations. Topic hint: {hint or 'none'}.

WORKSHEET:
\"\"\"{raw_text}\"\"\"

Return ONLY clean markdown with question numbers followed by the answer."""

    resp1 = client.chat.completions.create(model="llama-3.3-70b-versatile",
                                          messages=[{"role": "user", "content": prompt1}],
                                          temperature=0.2, max_tokens=8000)
    worksheet_md = resp1.choices[0].message.content
    w_path = f"uploads/COMP_{uuid.uuid4().hex[:8]}.docx"
    make_docx(worksheet_md, w_path)

    # 2. STEP A — Make a perfect outline + Works Cited first
    outline_prompt = f"""Using ONLY the worksheet answers below, create:
1. A strong, original title for a {target_words}-word essay
2. A detailed outline with 8–12 main sections (give each section a short heading)
3. A complete MLA Works Cited with exactly 8 real, verifiable peer-reviewed sources about this commodity (include DOIs when available)

COMPLETED WORKSHEET:
\"\"\"{worksheet_md}\"\"\"

Return ONLY JSON in this exact format:
{{"title": "...", "outline": ["Section 1 heading", "Section 2 heading", ...], "works_cited": "Full MLA Works Cited text"}}"""

    outline_resp = client.chat.completions.create(model="llama-3.3-70b-versatile",
                                                 messages=[{"role": "user", "content": outline_prompt}],
                                                 temperature=0.3, max_tokens=4000)
    try:
        plan = json.loads(outline_resp.choices[0].message.content)
    except:
        plan = {"title": "Commodity Supply Chain Analysis", "outline": ["Introduction", "Production", "Uses", "Supply Chain Risks", "Conclusion"], 
                "works_cited": "Works Cited\n(...fallback...)"}  # safety net

    # 3. STEP B — Write the essay section-by-section (this eliminates duplicates & controls length)
    sections = []
    words_so_far = 0
    words_per_section = target_words // len(plan["outline"])

    for i, heading in enumerate(plan["outline"], 1):
        section_prompt = f"""Write section {i} of the essay titled “{plan['title']}”.

Section heading: {heading}
Target length: ~{words_per_section} words (total essay must hit exactly {target_words} words when all sections are combined)

Write in the voice of a 55-year-old American senior business analyst with 30+ years experience.
First-person or confident “we/you”, tons of contractions, casual markers (“look,” “honestly,” “here’s the thing”), bursty sentences, start some with And/But/So/Because, one deliberate fragment every 300–400 words.
NO academic clichés. American English only.

Use facts ONLY from the worksheet and the Works Cited you already created.

WORKSHEET ANSWERS:
\"\"\"{worksheet_md}\"\"\"

WORKS CITED (use these sources):
{plan["works_cited"]}

Return ONLY the markdown for this section (no JSON, no explanation)."""

        resp = client.chat.completions.create(model="llama-3.3-70b-versatile",
                                              messages=[{"role": "user", "content": section_prompt}],
                                              temperature=0.65,
                                              max_tokens=4000)
        sections.append(f"# {heading}\n\n{resp.choices[0].message.content.strip()}")

    # Combine everything
    full_essay = f"# {plan['title']}\n\n" + "\n\n".join(sections) + f"\n\n{plan['works_cited']}"

    e_path = f"uploads/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    make_docx(full_essay, e_path)

    return {"worksheet": w_path, "essay": e_path}
