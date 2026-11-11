from datetime import datetime
import json

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import HTTPException
from starlette.requests import Request
from pathlib import Path

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")

LAWS_BASE_DIR = Path("./laws")

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )

@app.get("/book/{book}")
async def book(request: Request, book: str):
    file = Path(LAWS_BASE_DIR, book + ".json")

    if not file.is_file():
        raise HTTPException(detail=f"File {file} was not found", status_code=404)

    with open(file, "r") as f:
        bc = json.load(f)

    date = datetime.strptime(bc["updated"], "%Y-%m-%d")
    formatted = date.strftime("%d.%m.%Y")

    return templates.TemplateResponse(
        request=request,
        name="book.html",
        context={
            "book": bc,
            "book_updated": formatted
        }
    )

@app.get("/law/{id}")
async def get_law(request: Request, id: str):
    splitted = id.split("-", 2)
    book = splitted[0]

    file = Path(LAWS_BASE_DIR, book + ".json")

    if not file.is_file():
        raise HTTPException(detail=f"Law not found", status_code=404)

    with open(file, "r") as f:
        content = json.load(f)

    date = datetime.strptime(content["updated"], "%Y-%m-%d")
    formatted = date.strftime("%d.%m.%Y")

    law = next(
        (law for law in content["laws"] if law["id"] == id),
        None
    )

    if law is None:
        raise HTTPException(detail="Law not found", status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="law.html",
        context={
            "law": law,
            "book_id": content["id"],
            "book_abbr": content["abbr"],
            "book_prefix": content["prefix"],
            "book_name": content["name"],
            "book_updated": formatted
        }
    )

@app.post("/laws/all")
async def get_all_laws(request: Request):
    books = []

    for file in LAWS_BASE_DIR.rglob("*.json"):
        with open(file, "r") as f:
            content = json.load(f)
            books.append(content)

    return books