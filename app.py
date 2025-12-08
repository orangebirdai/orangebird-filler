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
    for line in md.split("\n"):
        line = line.strip()
        if not line:
            doc.add_paragraph("")
            continue
        # Make question lines bold and slightly larger
        if any(line.lstrip().startswith(f"{i}.") for i in range(1, 50)) or "?" in line:
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

    # STEP 1 — EXACT QUESTION-BY-QUESTION ANSWERS (no bullets, question + answer)
    prompt1 = f"""You are completing the worksheet below.
For every single question, write:
[Question number or exact question text]
[Your answer in one clear paragraph]

Do NOT use bullets. Do NOT skip any question.
Use {style} citation style. Topic hint: {hint or 'none'}.

WORKSHEET:
\"\"\"{raw_text}\"\"\"

Return ONLY the answers in this exact format:
1. What is the commodity?
   Lithium is a soft, silver-white alkali metal...

2. Where is it produced?
   The main producers are...

etc.
End with a Works Cited section."""

    resp1 = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt1}],
        temperature=0.1,
        max_tokens=8000
    )
    worksheet_md = resp1.choices[0].message.content
    w_path = f"uploads/COMP_{uuid.uuid4().hex[:8]}.docx"
    make_docx(worksheet_md, w_path)

    # STEP 2 — ESSAY BASED ON THE EXACT ANSWERS
    prompt2 = f"""Using ONLY the completed worksheet answers below, write a 1200–1500 word academic essay in {style}.
The essay must be about the exact same commodity and use only the facts from these answers.

COMPLETED WORKSHEET:
\"\"\"{worksheet_md}\"\"\"

Return ONLY clean markdown. No extra commentary."""

    resp2 = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt2}],
        temperature=0.4,
        max_tokens=8000
    )
    essay_md = resp2.choices[0].message.content
    e_path = f"uploads/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    make_docx(essay_md, e_path)

    return {"worksheet": w_path, "essay": e_path}

@app.get("/download/{path:path}")
async def dl(path: str):
    return FileResponse(path, filename=os.path.basename(path))
