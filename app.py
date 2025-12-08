import os
import uuid
import io
import json
import re
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from docx import Document
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

# (keep your extract_text, count_words, make_docx from the last version)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/go")
async def go(file: UploadFile = File(...), style: str = Form("MLA"), hint: str = Form(""), wordcount: str = Form("1500")):
    # ... your full worksheet + essay generation code from the last working version ...
    # (everything you had before — just make sure worksheet_file and essay_file are defined)

    worksheet_file = f"uploads/COMP_{uuid.uuid4().hex[:10]}.docx"
    make_docx(worksheet_md, worksheet_file)
    
    essay_file = f"uploads/ESSAY_{uuid.uuid4().hex[:10]}.docx"
    make_docx(full_essay, essay_file)

    # THIS IS THE ONLY THING THAT MATTERS — THIS PAGE SHOWS THE BUTTONS
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>OrangeBird - Done!</title>
        <style>
            body {{ font-family: Arial; text-align: center; padding: 60px; background: #f8f9fa; }}
            h1 {{ color: #27ae60; }}
            a {{ font-size: 22px; margin: 20px; padding: 15px 30px; background: #3498db; color: white; text-decoration: none; border-radius: 8px; }}
            a:hover {{ background: #2980b9; }}
        </style>
    </head>
    <body>
        <h1>DONE!</h1>
        <p><a href="/download/{worksheet_file}" download>Download Completed Worksheet</a></p>
        <p><a href="/download/{essay_file}" download>Download Full Essay ({target_words} words)</a></p>
        <br><br>
        <a href="/">← Generate Another</a>
    </body>
    </html>
    """)

@app.get("/download/{filename:path}")
async def download(filename: str):
    path = f"uploads/{filename}"
    if not os.path.exists(path):
        return HTMLResponse("File expired. Please generate again.", status_code=404)
    return FileResponse(path, filename=filename)
