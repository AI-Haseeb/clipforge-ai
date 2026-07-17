from __future__ import annotations  # enables future Python language features
import hashlib  # creates cryptographic hashes
import hmac  # creates and verifies keyed hashes
import os  # works with environment variables and OS paths
import secrets  # generates secure random tokens
import sqlite3  # uses SQLite databases
from datetime import datetime, timedelta, timezone  # works with dates and timestamps
from pathlib import Path  # provides object-oriented file paths
from typing import Optional  # adds type hint helpers

DB_PATH = Path(os.getenv("CLIPFORGE_AUTH_DB", "data/clipforge_auth.sqlite3"))
TOKEN_TTL_DAYS = int(os.getenv("CLIPFORGE_TOKEN_TTL_DAYS", "30"))
PBKDF2_ITERATIONS = int(os.getenv("CLIPFORGE_PASSWORD_ITERATIONS", "260000"))
def _utc_now() -> datetime:  # returns the current UTC time for auth/license timestamps
    return datetime.now(timezone.utc)
def _iso(dt: datetime) -> str:  # formats a datetime value as an ISO string
    return dt.astimezone(timezone.utc).isoformat()
def _connect() -> sqlite3.Connection:  # opens the local SQLite auth database connection
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
def init_auth_db() -> None:  # creates local auth tables if they do not exist
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                credits INTEGER NOT NULL DEFAULT 30,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
def _normalize_email(email: str) -> str:  # standardizes values before comparison or rendering
    return (email or "").strip().lower()
def _hash_password(password: str) -> str:  # hashes a password with salt for local auth storage
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"
def _verify_password(password: str, stored_hash: str) -> bool:  # checks a password against its stored local hash
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False
def _hash_token(token: str) -> str:  # hashes a session token before storing it locally
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
def _public_user(row: sqlite3.Row) -> dict:  # removes private auth fields before returning user data to the frontend
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "plan": row["plan"],
        "credits": row["credits"],
        "created_at": row["created_at"],
    }
def create_user(name: str, email: str, password: str) -> dict:  # creates an output artifact or runtime object
    clean_name = (name or "").strip()
    clean_email = _normalize_email(email)

    if len(clean_name) < 2:
        raise ValueError("Name must be at least 2 characters.")
    if "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise ValueError("Please enter a valid email address.")
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters.")

    now = _iso(_utc_now())
    user_id = secrets.token_urlsafe(16)

    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, name, email, password_hash, plan, credits, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'free', 30, ?, ?)
                """,
                (user_id, clean_name, clean_email, _hash_password(password), now, now),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except sqlite3.IntegrityError:
        raise ValueError("An account with this email already exists.")

    return _public_user(row)
def authenticate_user(email: str, password: str) -> Optional[dict]:  # validates login credentials and creates a local session
    clean_email = _normalize_email(email)
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (clean_email,)).fetchone()
    if not row or not _verify_password(password or "", row["password_hash"]):
        return None
    return _public_user(row)
def create_session(user_id: str) -> dict:  # creates an output artifact or runtime object
    token = secrets.token_urlsafe(32)
    now = _utc_now()
    expires_at = now + timedelta(days=TOKEN_TTL_DAYS)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_hash_token(token), user_id, _iso(now), _iso(expires_at)),
        )
    return {"token": token, "expires_at": _iso(expires_at)}
def get_user_by_token(token: str) -> Optional[dict]:  # returns a resolved value used by later code
    if not token:
        return None
    token_hash = _hash_token(token)
    now = _iso(_utc_now())
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
    return _public_user(row) if row else None
def delete_session(token: str) -> None:  # removes a local auth session token
    if not token:
        return
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
