import os
import uuid
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from docx import Document
from PyPDF2 import PdfReader
import io
import json
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
    else:  # .docx
        doc = Document(io.BytesIO(file_content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request):
    return templates.get_template("index.html").render({"request": request})

@app.post("/complete")
async def complete_document(
    file: UploadFile = File(...),
    citation_style: str = Form("MLA"),
    topic_hint: str = Form("")
):
    contents = await file.read()
    original_text = extract_text(contents, file.filename)
    
    prompt = f"""
You are an expert academic assistant. The user uploaded an incomplete assignment/worksheet/template.
Citation style requested: {citation_style}
Topic hint (if any): {topic_hint}

Document content:
\"\"\"{original_text}\"\"\"

Complete every blank, question, table, and section with concise, accurate, citation-rich answers.
Preserve all original numbering, headings, and formatting.
Add a Works Cited/References at the end in {citation_style}.
Return ONLY the full completed document text in clean markdown.
"""
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.3,
        max_tokens=8000
    )
    completed_text = chat_completion.choices[0].message.content

    # Save as new docx
    doc = Document()
    for line in completed_text.split("\n"):
        if line.strip():
            doc.add_paragraph(line)
    output_path = f"{UPLOAD_FOLDER}/COMPLETED_{uuid.uuid4().hex[:8]}_{file.filename}"
    doc.save(output_path)

    return {"completed_file": output_path, "markdown": completed_text}

@app.post("/essay")
async def generate_essay(file: UploadFile = File(...)):
    contents = await file.read()
    original_text = extract_text(contents, file.filename)

    prompt = f"""
Using the completed worksheet/assignment below, write a polished 1500-word academic essay 
(in the same citation style used in the document) that critically analyzes the commodity/global supply chain.
Use formal academic tone, strong thesis, and include all key facts from the worksheet.

Document:
\"\"\"{original_text}\"\"\"

Return the full essay in clean markdown with a title and Works Cited.
"""
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.4,
        max_tokens=8000
    )
    essay = chat_completion.choices[0].message.content

    essay_path = f"{UPLOAD_FOLDER}/ESSAY_{uuid.uuid4().hex[:8]}.docx"
    doc = Document()
    for line in essay.split("\n"):
        if line.strip():
            doc.add_paragraph(line)
    doc.save(essay_path)

    return {"essay_file": essay_path}

@app.get("/download/{filename:path}")
async def download(filename: str):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        return {"error": "File expired — please re-run the upload (free tier limitation)"}
    return FileResponse(
        file_path,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        filename=os.path.basename(file_path)
    )
