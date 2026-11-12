from contextlib import asynccontextmanager
from datetime import datetime
import json

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request
from pathlib import Path

def build_global_title_index():
    GLOBAL_TITLE_INDEX.clear()

    for file in LAWS_BASE_DIR.rglob("*.json"):
        with open(file, "r", encoding="utf-8") as f:
            content = json.load(f)

        book = {
            "id": content.get("id"),
            "abbr": content.get("abbr"),
            "name": content.get("name"),
            "scope": content.get("scope")
        }

        for law in content.get("laws", []):
            nr = str(law.get("nr", ""))
            name = str(law.get("name") or "")

            GLOBAL_TITLE_INDEX.append({
                "id": law["id"],
                "nr": nr,
                "name": name,
                "prefix": content.get("prefix", ""),
                "no_prefix": law.get("no_prefix", False),
                "book": book,
                "_search": f"{nr} {name}".lower()
            })

@asynccontextmanager
async def lifespan(app: FastAPI):
    build_global_title_index()
    yield
    GLOBAL_TITLE_INDEX.clear()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")

LAWS_BASE_DIR = Path("./laws")
GLOBAL_TITLE_INDEX: list[dict] = []

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

class GlobalTitleSearchRequest(BaseModel):
    query: str
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=150, ge=1, le=150)

@app.post("/laws/search/global/title")
async def search_all_titles(data: GlobalTitleSearchRequest):
    query = data.query.strip().lower()

    if not query:
        return {
            "query": query,
            "page": data.page,
            "limit": data.limit,
            "total": 0,
            "has_more": False,
            "results": []
        }

    matches = [
        entry for entry in GLOBAL_TITLE_INDEX
        if query in entry["_search"]
    ]

    total = len(matches)
    start = (data.page - 1) * data.limit
    end = start + data.limit

    results = [
        {
            key: value
            for key, value in entry.items()
            if key != "_search"
        }
        for entry in matches[start:end]
    ]

    return {
        "query": query,
        "page": data.page,
        "limit": data.limit,
        "total": total,
        "has_more": end < total,
        "results": results
    }