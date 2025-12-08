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
        line = line.rstrip()
        if line.startswith("# "): 
            doc.add_heading(line[2:], level=1)
        elif line.startswith("## "): 
            doc.add_heading(line[3:], level=2)
        elif any(line.startswith(x) for x in ["- ", "• ", "* ", "1. ", "2. ", "3. ", "4. ", "5. ", "6. ", "7. ", "8. ", "9. "]):
            doc.add_paragraph(line[line.find(" ")+1:].strip(), style="List Bullet")
        elif line:
            doc.add_paragraph(line)
        else:
            doc.add_paragraph("")
    doc.save(path)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/go")
async def go(file: UploadFile = File(...), style: str = Form("MLA"), hint: str = Form("")):
    text = extract_text(await file.read(), file.filename)

    # 1. PERFECT WORKSHEET — answers every question in order
    prompt1 = f"""You are an A+ student completing the exact worksheet below.
Answer EVERY numbered or bulleted question EXACTLY in order using the same numbering.
Do NOT write an essay. Do NOT skip any question.
Use {style} citation style. Topic hint: {hint or 'none'}.

WORKSHEET TO COMPLETE (answer each part in order):
\"\"\"{text}\"\"\"

Return ONLY clean markdown.
Use the exact same question numbers and headings that appear in the worksheet.
Put the answer directly after each question.
End with a Works Cited section."""

    resp1 = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt1}],
        temperature=0.3, max_tokens=8000)
    w_path = f"uploads/COMP_{uuid.uuid4().hex[:8]}.docx"
    make_docx(resp1.choices[0].message.content, w_path)

    # 2. PERFECT ESSAY — now 100% about the same commodity
    prompt2 = f"""You are an expert academic writer.
Write a polished 1500-word essay in {style} about the commodity discussed in the worksheet below.
Use all the information from the worksheet answers.
Strong thesis, formal tone, proper citations.

WORKSHEET ANSWERS:
\"\"\"{resp1.choices[0].message.content}\"\"\"

Return ONLY clean markdown."""
    
    resp2 = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt2}],
        temperature=0.4, max_tokens=8000)
    e_path = f"uploads/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    make_docx(resp2.choices[0].message.content, e_path)

    return {"worksheet": w_path, "essay": e_path}

@app.get("/download/{path:path}")
async def dl(path: str):
    return FileResponse(path, filename=os.path.basename(path))
