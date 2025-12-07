import os
import uuid
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from docx import Document
from docx.shared import Inches
from PyPDF2 import PdfReader
import io
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def extract_text(file_content: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(file_content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        doc = Document(io.BytesIO(file_content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

def create_docx_from_markdown(md_text: str, output_path: str):
    doc = Document()
    doc.add_heading("OrangeBird Filler – Completed Assignment", 0)
    for line in md_text.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        elif line.startswith("- ") or line.startswith("• "):
            doc.add_paragraph(line[2:], style="List Bullet")
        elif line:
            doc.add_paragraph(line)
        else:
            doc.add_paragraph("")  # blank line
    doc.save(output_path)

@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request):
    return templates.get_template("index.html").render({"request": request})

@app.post("/complete")
async def complete_document(file: UploadFile = File(...), citation_style: str = Form("MLA"), topic_hint: str = Form("")):
    contents = await file.read()
    original_text = extract_text(contents, file.filename)
    
    prompt = f"""Complete this entire assignment perfectly in {citation_style} style. Topic hint: {topic_hint or 'none'}.
Document:
\"\"\"{original_text}\"\"\"
Return ONLY clean, properly formatted markdown with headings, bullets, and a Works Cited section at the end."""
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=8000
    )
    completed_md = response.choices[0].message.content

    output_path = f"{UPLOAD_FOLDER}/COMPLETED_{uuid.uuid4().hex[:8]}.docx"
    create_docx_from_markdown(completed_md, output_path)

    return {"completed_file": output_path}

@app.post("/essay")
async def generate_essay(file: UploadFile = File(...), citation_style: str = Form("MLA")):
    contents = await file.read()
    original_text = extract_text(contents, file.filename)

    prompt = f"""Write a full 1500-word academic essay based on this completed worksheet.
Use formal tone, strong thesis, and proper {citation_style} citations.
Document:
\"\"\"{original_text}\"\"\"
Return clean markdown only."""
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=8000
    )
    essay_md = response.choices[0].message.content

    essay_path = f"{UPLOAD_FOLDER}/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    create_docx_from_markdown(essay_md, essay_path)

    return {"essay_file": essay_path}
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=8000
    )
    essay_md = response.choices[0].message.content

    essay_path = f"{UPLOAD_FOLDER}/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    create_docx_from_markdown(essay_md, essay_path)

    return {"essay_file": essay_path}

@app.get("/download/{filename:path}")
async def download(filename: str):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        return {"error": "File expired — re-run the upload"}
    return FileResponse(file_path, filename=os.path.basename(file_path),
                       media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
