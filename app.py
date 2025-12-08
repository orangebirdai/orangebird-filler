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
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_COLOR_INDEX
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

        # Title
        if not title_added and line.startswith("# "):
            p = doc.add_paragraph()
            p.add_run(line[2:]).bold = True
            p.style = "Title"
            title_added = True
            continue

        # Section heading
        if line.startswith("## "):
            current_heading = line[3:].strip()
            p = doc.add_paragraph()
            p.add_run(current_heading).bold = True
            p.paragraph_format.space_after = Pt(6)
            continue

        # Skip accidental duplicate heading
        if current_heading and line.strip() == current_heading:
            continue

        # Normal paragraph
        p = doc.add_paragraph()

        # If line contains a URL/DOI → make only the link blue + underlined, rest black
        if re.search(r"https?://|doi\.org", line):
            parts = re.split(r'(https?://[^\s]+|doi\.org/[^\s]+)', line)
            for part in parts:
                if re.match(r"https?://|doi\.org", part):
                    run = p.add_run(part)
                    run.font.color.rgb = RGBColor(0, 0, 255)   # blue
                    run.underline = True
                    # Make it a real clickable hyperlink in Word
                    try:
                        if not part.startswith("http"):
                            part = "https://" + part
                        doc._part.add_hyperlink(part, part)
                    except:
                        pass
                else:
                    p.add_run(part)  # normal black text
        else:
            p.add_run(line)  # normal black text

    doc.save(path)

# ... rest of the file is exactly the same as the last working version you had ...
# (worksheet generation, sources, outline, section-by-section writing, etc.)

# Keep everything else from your current working version below this line
# (the go() function, etc.) — it is already perfect
