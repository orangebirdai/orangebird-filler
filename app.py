import os
import uuid
import io
import json
import asyncio
import re                # ←←← THIS WAS MISSING
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

# (extract_text, make_docx, count_words — all unchanged from the last version)

def count_words(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))

# ... rest of the file exactly as I sent last time ...
