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
async def go(
    file: UploadFile = File(...),
    style: str = Form("MLA"),
    hint: str = Form(""),
    wordcount: str = Form("1500")  # ←←← NEW INPUT FIELD
):
    raw_text = extract_text(await file.read(), file.filename)
    try:
        wc = int(wordcount)
        wc = max(100, min(8000, wc))  # clamp between 100–8000
    except:
        wc = 1500

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

    # 2. ESSAY — NOW WITH CUSTOM WORD COUNT + ALL YOUR ORIGINAL RULES
    prompt2 = f"""Write an essay of exactly {wc} words.

First, invent a strong, original title that perfectly fits the commodity in the worksheet below.

Write it exactly like a 55-year-old American senior business analyst with 30+ years of real-world experience (someone who’s lived through every boom and bust since the 1980s) explaining the topic to a sharp grad student or a skeptical client. Use American English only.

Voice rules:
- First-person (“I’ve seen…”) or confident “we/you” where it feels natural
- Plenty of contractions (it’s, don’t, we’ve, you’re)
- Drop in casual markers once or twice per paragraph: “look,” “honestly,” “here’s the thing,” “I’ve found over the years,” “you know what I’ve noticed” — keep it light, never forced

Style rules (non-negotiable):
- Heavy burstiness: mix 5–8-word punchy sentences with occasional 25–35-word winding ones. Never two sentences in a row the same length.
- Start some sentences with And, But, So, or Because.
- Use commas, no em-dashes, you can use parentheses, and one deliberate sentence fragment every 300–400 words.
- Ban academic clichés completely: no “however,” “moreover,” “in conclusion,” “paradigm shift,” “ripple effects,” “it is evident that,” etc.
- Let ideas flow conversationally — a slightly abrupt shift between thoughts is fine.
- Plain, precise American English only; swap fancy jargon for straightforward words when meaning stays the same.

Sources & citations:
- Use at least 7 real, verifiable, peer-reviewed journal articles (no hallucinations).
- Weave them in naturally (“Back in 2021 Bonadio and his team proved…”, “that Journal of International Economics paper we all leaned on — check the DOI below”).
- Keep every citation and DOI link intact.
- End with a proper MLA “Works Cited” section.

Target Flesch reading ease 60–70 — smart, readable, like a top-tier consulting report or a killer grad seminar paper. Never slip into stiff, detached third-person academic tone.

Use ONLY the facts from the completed worksheet below as the foundation.

COMPLETED WORKSHEET ANSWERS:
\"\"\"{worksheet_md}\"\"\"

Deliver the complete essay in clean markdown. Start with the title on its own line."""

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
