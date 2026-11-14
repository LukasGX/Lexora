import hashlib
import secrets

from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

from database.db import get_db


password_hasher = PasswordHasher()

SESSION_DURATION = timedelta(days=7)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register_user(username: str, email: str, password: str) -> int:
    username = username.strip()
    email = email.strip().lower()

    if len(username) < 3 or len(username) > 32:
        raise ValueError("Ungültiger Benutzername.")

    if len(password) < 8:
        raise ValueError("Das Passwort muss mindestens 12 Zeichen lang sein.")

    if len(password) > 1024:
        raise ValueError("Das Passwort ist zu lang.")

    password_hash = hash_password(password)

    try:
        with get_db() as db:
            cursor = db.execute(
                """
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
                """,
                (username, email, password_hash)
            )

            return cursor.lastrowid

    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise ValueError(
                "Benutzername oder E-Mail-Adresse bereits vergeben."
            ) from exc
        raise


def authenticate_user(identifier: str, password: str):
    identifier = identifier.strip()

    with get_db() as db:
        user = db.execute(
            """
            SELECT id, username, email, password_hash
            FROM users
            WHERE username = ? COLLATE NOCASE
               OR email = ? COLLATE NOCASE
            """,
            (identifier, identifier)
        ).fetchone()

    if user is None:
        return None

    if not verify_password(password, user["password_hash"]):
        return None

    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"]
    }


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)

    expires_at = (
        datetime.now(timezone.utc) + SESSION_DURATION
    ).isoformat()

    with get_db() as db:
        db.execute(
            """
            INSERT INTO sessions (token_hash, user_id, expires_at)
            VALUES (?, ?, ?)
            """,
            (token_hash, user_id, expires_at)
        )

    return token


def get_session_user(token: str):
    if not token:
        return None

    token_hash = hash_token(token)
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        session = db.execute(
            """
            SELECT users.id, users.username, users.email
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ?
              AND sessions.expires_at > ?
            """,
            (token_hash, now)
        ).fetchone()

    if session is None:
        return None

    return dict(session)


def revoke_session(token: str):
    if not token:
        return

    token_hash = hash_token(token)

    with get_db() as db:
        db.execute(
            "DELETE FROM sessions WHERE token_hash = ?",
            (token_hash,)
        )


def cleanup_expired_sessions():
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        db.execute(
            "DELETE FROM sessions WHERE expires_at <= ?",
            (now,)
        )