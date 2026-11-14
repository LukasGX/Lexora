from contextlib import asynccontextmanager
from datetime import datetime
import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

from auth import authenticate_user, create_session, register_user, revoke_session
from database.db import initialize_database
from dependencies import get_current_user, get_user

load_dotenv()

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

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SECRET_KEY"],
    session_cookie="lexora_session",
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=True,
)

templates = Jinja2Templates(directory="templates")

initialize_database()

app.mount("/static", StaticFiles(directory="static"), name="static")

LAWS_BASE_DIR = Path("./laws")
GLOBAL_TITLE_INDEX: list[dict] = []
SESSION_COOKIE = "lexora_session"

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": get_user(request),
            "laws": all_books(),
            "active_book": "home"
        }
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
            "user": get_user(request),
            "laws": all_books(),
            "active_book": bc["id"],
            "book": bc,
            "book_updated": formatted
        }
    )

@app.get("/law/{id}")
async def get_law(request: Request, id: str, highlight: str | None = None):
    splitted = id.split("-", 2)
    book = splitted[0]

    file = Path(LAWS_BASE_DIR, book + ".json")

    if not file.is_file():
        raise HTTPException(detail="Law not found", status_code=404)

    with open(file, "r", encoding="utf-8") as f:
        content = json.load(f)

    date = datetime.strptime(content["updated"], "%Y-%m-%d")
    formatted = date.strftime("%d.%m.%Y")

    law = next(
        (law for law in content["laws"] if law["id"] == id),
        None
    )

    if law is None:
        raise HTTPException(detail="Law not found", status_code=404)

    # Load cross-references
    links_file = Path(LAWS_BASE_DIR, book + ".link.json")
    law_links = []

    if links_file.is_file():
        with open(links_file, "r", encoding="utf-8") as f:
            link_data = json.load(f)

        law_links = [
            link
            for link in link_data.get("links", [])
            if link["source"] == id
        ]

    return templates.TemplateResponse(
        request=request,
        name="law.html",
        context={
            "user": get_user(request),
            "laws": all_books(),
            "active_book": content["id"],
            "law": law,
            "highlight": highlight,
            "law_links": law_links,
            "book_id": content["id"],
            "book_abbr": content["abbr"],
            "book_prefix": content["prefix"],
            "book_name": content["name"],
            "book_updated": formatted
        }
    )

@app.post("/laws/all")
async def get_all_laws(request: Request):
    return all_books()

def all_books():
    books = []
    
    for file in LAWS_BASE_DIR.rglob("*.json"):
        if file.name.endswith(".link.json"):
            continue

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

@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...)
):
    if password != password_confirm:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "Die Passwörter stimmen nicht überein."},
            status_code=400
        )

    try:
        user_id = register_user(username, email, password)
    except ValueError as exc:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": str(exc)},
            status_code=400
        )

    token = create_session(user_id)

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/"
    )

    return response


@app.post("/login")
async def login(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...)
):
    user = authenticate_user(identifier, password)

    if user is None:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Ungültige Anmeldedaten."},
            status_code=401
        )

    # Alte Session widerrufen, falls vorhanden
    old_token = request.cookies.get(SESSION_COOKIE)
    if old_token:
        revoke_session(old_token)

    token = create_session(user["id"])

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/"
    )

    return response

@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "user": get_user(request),
            "laws": all_books(),
            "active_book": "account",
            "error": None
        }
    )

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "user": get_user(request),
            "laws": all_books(),
            "active_book": "account",
            "error": None
        }
    )

@app.get("/account")
async def account(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="account.html",
        context={
            "user": get_user(request),
            "laws": all_books(),
            "active_book": "account"
        }
    )

@app.get("/logout")
@app.post("/logout")
async def logout_post(request: Request):
    token = request.cookies.get(SESSION_COOKIE)

    if token:
        revoke_session(token)

    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax"
    )

    return response