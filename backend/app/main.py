from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import random
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATABASE_PATH = PROJECT_ROOT / "data" / "motiva.db"
SESSION_COOKIE = "motiva_session"
SESSION_DAYS = 30
PASSWORD_ITERATIONS = 310_000
STARTER_DATA_PATH = Path(__file__).with_name("seed_lessons.json")

app = FastAPI(title="Motiva Language Learning API", version="1.0.0")

LANGUAGES = {
    "en": {"code": "en", "name": "English", "flag": "🇬🇧"},
    "es": {"code": "es", "name": "Español", "flag": "🇪🇸"},
}

def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    db = connect()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize_database() -> None:
    with database() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'learner',
                profile_image TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY,
                language TEXT NOT NULL DEFAULT 'en',
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                level TEXT NOT NULL,
                description TEXT NOT NULL,
                accent TEXT NOT NULL,
                owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS lesson_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                term TEXT NOT NULL,
                translation TEXT NOT NULL,
                pronunciation TEXT NOT NULL,
                example TEXT NOT NULL,
                example_translation TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS review_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL REFERENCES lesson_items(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
                reviewed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS quiz_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                source_item_id INTEGER REFERENCES lesson_items(id) ON DELETE CASCADE,
                language TEXT NOT NULL,
                category TEXT NOT NULL,
                level TEXT NOT NULL DEFAULT 'Beginner',
                question_type TEXT NOT NULL DEFAULT 'multiple_choice',
                prompt TEXT NOT NULL,
                choices_json TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                explanation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(source_item_id, question_type)
            );
            CREATE TABLE IF NOT EXISTS quiz_sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                language TEXT NOT NULL,
                category TEXT NOT NULL,
                level TEXT NOT NULL,
                title TEXT NOT NULL,
                question_count INTEGER NOT NULL CHECK (question_count > 0),
                duration_seconds INTEGER NOT NULL DEFAULT 300,
                correct_count INTEGER,
                score INTEGER,
                started_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS quiz_session_questions (
                session_id TEXT NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
                question_id INTEGER NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                PRIMARY KEY (session_id, question_id),
                UNIQUE (session_id, position)
            );
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                session_id TEXT REFERENCES quiz_sessions(id) ON DELETE CASCADE,
                is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
                answered_at TEXT NOT NULL
            );
            """
        )
        user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
        if "role" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'learner'")
        if "profile_image" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN profile_image TEXT")
        lesson_columns = {row["name"] for row in db.execute("PRAGMA table_info(lessons)")}
        if "language" not in lesson_columns:
            db.execute("ALTER TABLE lessons ADD COLUMN language TEXT NOT NULL DEFAULT 'en'")
        if "owner_id" not in lesson_columns:
            db.execute("ALTER TABLE lessons ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        review_columns = {row["name"] for row in db.execute("PRAGMA table_info(review_events)")}
        if "user_id" not in review_columns:
            db.execute("ALTER TABLE review_events ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        attempt_columns = {row["name"] for row in db.execute("PRAGMA table_info(quiz_attempts)")}
        if "session_id" not in attempt_columns:
            db.execute("ALTER TABLE quiz_attempts ADD COLUMN session_id TEXT REFERENCES quiz_sessions(id) ON DELETE CASCADE")
        quiz_session_columns = {row["name"] for row in db.execute("PRAGMA table_info(quiz_sessions)")}
        if "duration_seconds" not in quiz_session_columns:
            db.execute("ALTER TABLE quiz_sessions ADD COLUMN duration_seconds INTEGER NOT NULL DEFAULT 300")
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_quiz_attempt_session_question "
            "ON quiz_attempts(session_id, question_id) WHERE session_id IS NOT NULL"
        )
        duplicate_course = db.execute(
            """SELECT 1 FROM lessons
            GROUP BY language, lower(trim(title)), category, level
            HAVING COUNT(*) > 1 LIMIT 1"""
        ).fetchone()
        if duplicate_course is None:
            db.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_lessons_unique_course
                ON lessons(language, lower(trim(title)), category, level)"""
            )
        # Reconcile starter content on every startup. This adds newly shipped courses
        # to existing databases while leaving administrator edits and learner activity intact.
        seed_data = json.loads(STARTER_DATA_PATH.read_text(encoding="utf-8"))
        seed_ids = set()
        seed_course_keys = set()
        for lesson in seed_data:
            course_key = (
                lesson["language"], lesson["title"].strip().casefold(),
                lesson["category"], lesson["level"],
            )
            if lesson["id"] in seed_ids or course_key in seed_course_keys:
                continue
            seed_ids.add(lesson["id"])
            seed_course_keys.add(course_key)
            existing_id = db.execute("SELECT id FROM lessons WHERE id = ?", (lesson["id"],)).fetchone()
            if existing_id is None:
                duplicate = db.execute(
                    """SELECT id FROM lessons WHERE language = ?
                    AND lower(trim(title)) = lower(?) AND category = ? AND level = ?""",
                    (lesson["language"], lesson["title"].strip(), lesson["category"], lesson["level"]),
                ).fetchone()
                if duplicate is not None:
                    continue
                db.execute(
                    """INSERT INTO lessons
                    (id, language, title, category, level, description, accent, owner_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
                    tuple(lesson[key] for key in ("id", "language", "title", "category", "level", "description", "accent")),
                )
            item_count = db.execute(
                "SELECT COUNT(*) FROM lesson_items WHERE lesson_id = ?", (lesson["id"],)
            ).fetchone()[0]
            if item_count == 0:
                db.executemany(
                    """INSERT INTO lesson_items
                    (lesson_id, term, translation, pronunciation, example, example_translation)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    [(lesson["id"], *item) for item in lesson["items"]],
                )
        seed_default_quiz_questions(db)
        bootstrap_admin(db)


def seed_default_quiz_questions(db: sqlite3.Connection) -> None:
    cards = db.execute(
        """SELECT i.*, l.language, l.category, l.level, l.title AS lesson_title,
        l.owner_id AS lesson_owner FROM lesson_items i JOIN lessons l ON l.id = i.lesson_id
        ORDER BY i.id"""
    ).fetchall()
    for card in cards:
        siblings = [
            row for row in cards
            if row["language"] == card["language"] and row["id"] != card["id"]
            and (row["lesson_owner"] is None or row["lesson_owner"] == card["lesson_owner"])
        ]
        language_name = LANGUAGES[card["language"]]["name"]
        examples = [row["translation"] for row in siblings]
        translations = list(dict.fromkeys([card["translation"], *examples]))[:4]
        reverse_terms = list(dict.fromkeys([card["term"], *(row["term"] for row in siblings)]))[:4]
        sentence_translations = list(dict.fromkeys([
            card["example_translation"], *(row["example_translation"] for row in siblings)
        ]))[:4]
        explanation = (
            f"{card['term']} means {card['translation']}. "
            f"Example: {card['example']} — {card['example_translation']} "
            f"Pronunciation: {card['pronunciation']}"
        )
        questions = [
            (
                "meaning",
                f"Choose the French translation of: “{card['term']}”",
                translations,
                card["translation"],
            ),
            (
                "recall",
                f"Which {language_name} word or phrase matches: “{card['translation']}”",
                reverse_terms,
                card["term"],
            ),
            (
                "sentence",
                f"Choose the French translation of: “{card['example']}”",
                sentence_translations,
                card["example_translation"],
            ),
        ]
        for question_type, prompt, choices, answer in questions:
            if len(choices) < 3:
                continue
            db.execute(
                """INSERT OR IGNORE INTO quiz_questions
                (lesson_id, source_item_id, language, category, level, question_type,
                 prompt, choices_json, correct_answer, explanation, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    card["lesson_id"], card["id"], card["language"], card["category"],
                    card["level"], question_type, prompt, json.dumps(choices, ensure_ascii=False),
                    answer, explanation, datetime.now(timezone.utc).isoformat(),
                ),
            )


def refresh_seed_questions_for_card(db: sqlite3.Connection, item_id: int) -> None:
    card = db.execute(
        """SELECT i.*, l.language, l.category, l.level, l.owner_id AS lesson_owner
        FROM lesson_items i JOIN lessons l ON l.id = i.lesson_id WHERE i.id = ?""",
        (item_id,),
    ).fetchone()
    if card is None:
        return
    siblings = db.execute(
        """SELECT i.term, i.translation, i.example_translation FROM lesson_items i JOIN lessons l ON l.id = i.lesson_id
        WHERE l.language = ? AND i.id != ? AND (l.owner_id IS NULL OR l.owner_id = ?)""",
        (card["language"], item_id, card["lesson_owner"] or -1),
    ).fetchall()
    explanation = (
        f"{card['term']} means {card['translation']}. Example: {card['example']} — "
        f"{card['example_translation']} Pronunciation: {card['pronunciation']}"
    )
    for question_type, prompt, options, answer in [
        ("meaning", f"Choose the French translation of: “{card['term']}”",
         list(dict.fromkeys([card["translation"], *(row["translation"] for row in siblings)]))[:4],
         card["translation"]),
        ("recall", f"Which {LANGUAGES[card['language']]['name']} word or phrase matches: “{card['translation']}”",
         list(dict.fromkeys([card["term"], *(row["term"] for row in siblings)]))[:4], card["term"]),
        ("sentence", f"Choose the French translation of: “{card['example']}”",
         list(dict.fromkeys([card["example_translation"], *(row["example_translation"] for row in siblings)]))[:4],
         card["example_translation"]),
    ]:
        db.execute(
            """UPDATE quiz_questions SET prompt = ?, choices_json = ?, correct_answer = ?, explanation = ?
            WHERE source_item_id = ? AND question_type = ?""",
            (prompt, json.dumps(options, ensure_ascii=False), answer, explanation, item_id, question_type),
        )


def bootstrap_admin(db: sqlite3.Connection) -> None:
    username = os.getenv("MOTIVA_ADMIN_USERNAME", "").strip()
    password = os.getenv("MOTIVA_ADMIN_PASSWORD", "")
    if not username and not password:
        return
    if not re.fullmatch(r"[A-Za-z0-9_]{3,24}", username):
        raise RuntimeError("MOTIVA_ADMIN_USERNAME must contain 3 to 24 letters, numbers, or underscores.")
    if len(password) < 8:
        raise RuntimeError("MOTIVA_ADMIN_PASSWORD must contain at least 8 characters.")
    existing = db.execute(
        "SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)
    ).fetchone()
    if existing:
        db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (existing["id"],))
    else:
        db.execute(
            "INSERT INTO users (username, password_hash, created_at, role) VALUES (?, ?, ?, 'admin')",
            (username, hash_password(password), datetime.now(timezone.utc).isoformat()),
        )


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hash_password(password, bytes.fromhex(salt_hex)).split("$")[-1]
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with database() as db:
        db.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_digest(token), user_id, expires.isoformat()),
        )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=False,  # Set secure=True when the app is deployed behind HTTPS.
        samesite="lax",
        path="/",
    )


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Please sign in to continue")
    with database() as db:
        row = db.execute(
            """SELECT u.id, u.username, u.role, u.profile_image FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > ?""",
            (token_digest(token), datetime.now(timezone.utc).isoformat()),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again")
    return dict(row)


def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required")
    return user


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=24, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class ProfilePhotoInput(BaseModel):
    data_url: str = Field(min_length=30, max_length=2_800_000)


class LessonInput(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    language: Literal["en", "es"]
    category: Literal["Vocabulary", "Travel", "Grammar"]
    description: str = Field(min_length=3, max_length=180)


class AdminLessonInput(LessonInput):
    level: Literal["Beginner", "Intermediate", "Advanced"] = "Beginner"


class CardInput(BaseModel):
    term: str = Field(min_length=1, max_length=160)
    translation: str = Field(min_length=1, max_length=160)
    pronunciation: str = Field(min_length=1, max_length=100)
    example: str = Field(min_length=1, max_length=220)
    example_translation: str = Field(min_length=1, max_length=220)


class ReviewSubmission(BaseModel):
    item_id: int = Field(gt=0)
    correct: bool


class QuizQuestionInput(BaseModel):
    lesson_id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=5, max_length=240)
    choices: list[str] = Field(min_length=3, max_length=6)
    correct_answer: str = Field(min_length=1, max_length=180)
    explanation: str = Field(min_length=5, max_length=500)
    level: Literal["Beginner", "Intermediate", "Advanced"] = "Beginner"


class QuizAnswer(BaseModel):
    session_id: str = Field(min_length=32, max_length=32)
    question_id: int = Field(gt=0)
    answer: str = Field(max_length=180)


class QuizSessionAction(BaseModel):
    session_id: str = Field(min_length=32, max_length=32)


@app.on_event("startup")
def on_startup() -> None:
    initialize_database()


@app.post("/api/auth/register", status_code=201)
def register(credentials: Credentials, response: Response) -> dict:
    username = credentials.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Choose a username")
    try:
        with database() as db:
            cursor = db.execute(
                "INSERT INTO users (username, password_hash, created_at, role) VALUES (?, ?, ?, 'learner')",
                (username, hash_password(credentials.password), datetime.now(timezone.utc).isoformat()),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="That username is already taken") from error
    create_session(response, user_id)
    return {"id": user_id, "username": username, "role": "learner", "profile_image": None}


@app.post("/api/auth/login")
def login(credentials: Credentials, response: Response) -> dict:
    with database() as db:
        user = db.execute(
            "SELECT id, username, password_hash, role, profile_image FROM users WHERE username = ? COLLATE NOCASE",
            (credentials.username.strip(),),
        ).fetchone()
    if user is None or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Username or password is incorrect")
    create_session(response, user["id"])
    return {"id": user["id"], "username": user["username"], "role": user["role"], "profile_image": user["profile_image"]}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with database() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest(token),))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    return {"logged_out": True}


@app.get("/api/auth/me")
def who_am_i(user: dict = Depends(get_current_user)) -> dict:
    return user


@app.put("/api/profile/photo")
def save_profile_photo(photo: ProfilePhotoInput, user: dict = Depends(get_current_user)) -> dict:
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})", photo.data_url)
    if match is None:
        raise HTTPException(status_code=400, detail="Choose a PNG, JPEG, or WebP image.")
    mime_subtype, encoded = match.groups()
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=400, detail="The selected image could not be read.") from error
    if not image_bytes or len(image_bytes) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Profile photos must be 2 MB or smaller.")
    valid_signature = (
        (mime_subtype == "png" and image_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        or (mime_subtype == "jpeg" and image_bytes.startswith(b"\xff\xd8\xff"))
        or (mime_subtype == "webp" and image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP")
    )
    if not valid_signature:
        raise HTTPException(status_code=400, detail="The file contents do not match a supported image type.")
    with database() as db:
        db.execute("UPDATE users SET profile_image = ? WHERE id = ?", (photo.data_url, user["id"]))
    return {"profile_image": photo.data_url}


@app.delete("/api/profile/photo")
def remove_profile_photo(user: dict = Depends(get_current_user)) -> dict:
    with database() as db:
        db.execute("UPDATE users SET profile_image = NULL WHERE id = ?", (user["id"],))
    return {"profile_image": None}


@app.get("/api/admin/overview")
def admin_overview(admin: dict = Depends(get_admin_user)) -> dict:
    with database() as db:
        lessons = db.execute("SELECT COUNT(*) FROM lessons WHERE owner_id IS NULL").fetchone()[0]
        cards = db.execute(
            "SELECT COUNT(*) FROM lesson_items i JOIN lessons l ON l.id = i.lesson_id WHERE l.owner_id IS NULL"
        ).fetchone()[0]
        questions = db.execute(
            "SELECT COUNT(*) FROM quiz_questions q JOIN lessons l ON l.id = q.lesson_id WHERE l.owner_id IS NULL"
        ).fetchone()[0]
        attempts = db.execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0]
    return {"lessons": lessons, "cards": cards, "questions": questions, "attempts": attempts}


@app.get("/api/admin/learners")
def admin_list_learner_progress(admin: dict = Depends(get_admin_user)) -> list[dict]:
    with database() as db:
        learners = db.execute(
            "SELECT id, username, created_at FROM users WHERE role = 'learner' ORDER BY username COLLATE NOCASE"
        ).fetchall()
        results = []
        for learner in learners:
            activity = db.execute(
                """SELECT COUNT(*) AS activity_count, MAX(answered_at) AS last_activity FROM (
                    SELECT reviewed_at AS answered_at FROM review_events WHERE user_id = ?
                    UNION ALL
                    SELECT answered_at FROM quiz_attempts WHERE user_id = ?
                )""",
                (learner["id"], learner["id"]),
            ).fetchone()
            courses = db.execute(
                """SELECT l.id, l.title, l.language, l.category, l.level,
                COUNT(DISTINCT i.id) AS item_count,
                COUNT(DISTINCT r.item_id) AS cards_studied,
                COALESCE(ROUND(100.0 * COUNT(DISTINCT r.item_id) / NULLIF(COUNT(DISTINCT i.id), 0)), 0) AS study_percent,
                COALESCE(qp.quiz_answers, 0) AS quiz_answers,
                COALESCE(qp.quiz_accuracy, 0) AS quiz_accuracy
                FROM lessons l LEFT JOIN lesson_items i ON i.lesson_id = l.id
                LEFT JOIN review_events r ON r.item_id = i.id AND r.user_id = ?
                LEFT JOIN (
                    SELECT q.lesson_id, COUNT(*) AS quiz_answers,
                    ROUND(100.0 * SUM(a.is_correct) / COUNT(*)) AS quiz_accuracy
                    FROM quiz_attempts a JOIN quiz_questions q ON q.id = a.question_id
                    WHERE a.user_id = ? GROUP BY q.lesson_id
                ) qp ON qp.lesson_id = l.id
                WHERE l.owner_id IS NULL GROUP BY l.id ORDER BY l.language, l.level, l.category, l.title""",
                (learner["id"], learner["id"]),
            ).fetchall()
            results.append({
                "id": learner["id"],
                "username": learner["username"],
                "created_at": learner["created_at"],
                "activity_count": activity["activity_count"],
                "last_activity": activity["last_activity"],
                "courses": [dict(course) for course in courses],
            })
    return results


@app.get("/api/admin/lessons")
def admin_list_lessons(admin: dict = Depends(get_admin_user)) -> list[dict]:
    with database() as db:
        rows = db.execute(
            """SELECT l.*, COUNT(DISTINCT i.id) AS item_count,
            COUNT(DISTINCT q.id) AS question_count
            FROM lessons l LEFT JOIN lesson_items i ON i.lesson_id = l.id
            LEFT JOIN quiz_questions q ON q.lesson_id = l.id
            WHERE l.owner_id IS NULL GROUP BY l.id ORDER BY l.language, l.category, l.title"""
        ).fetchall()
    return [dict(row) for row in rows]


def ensure_course_is_unique(
    db: sqlite3.Connection, lesson: AdminLessonInput, exclude_id: str | None = None
) -> None:
    query = """SELECT id FROM lessons WHERE language = ?
    AND lower(trim(title)) = lower(?) AND category = ? AND level = ?"""
    values: tuple[object, ...] = (
        lesson.language, lesson.title.strip(), lesson.category, lesson.level,
    )
    if exclude_id is not None:
        query += " AND id != ?"
        values += (exclude_id,)
    duplicate = db.execute(query, values).fetchone()
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail="A course with this language, title, category, and level already exists.",
        )


@app.post("/api/admin/lessons", status_code=201)
def admin_create_lesson(lesson: AdminLessonInput, admin: dict = Depends(get_admin_user)) -> dict:
    lesson_id = f"shared-{uuid.uuid4().hex}"
    accents = {"Vocabulary": "mint", "Travel": "peach", "Grammar": "lilac"}
    with database() as db:
        ensure_course_is_unique(db, lesson)
        db.execute(
            """INSERT INTO lessons (id, language, title, category, level, description, accent, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
            (lesson_id, lesson.language, lesson.title.strip(), lesson.category, lesson.level,
             lesson.description.strip(), accents.get(lesson.category, "mint")),
        )
        row = db.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    return {**dict(row), "item_count": 0, "question_count": 0}


@app.get("/api/admin/lessons/{lesson_id}")
def admin_get_lesson(lesson_id: str, admin: dict = Depends(get_admin_user)) -> dict:
    with database() as db:
        lesson = db.execute(
            "SELECT * FROM lessons WHERE id = ? AND owner_id IS NULL", (lesson_id,)
        ).fetchone()
        if lesson is None:
            raise HTTPException(status_code=404, detail="Shared lesson not found")
        items = db.execute(
            "SELECT * FROM lesson_items WHERE lesson_id = ? ORDER BY id", (lesson_id,)
        ).fetchall()
        questions = db.execute(
            "SELECT * FROM quiz_questions WHERE lesson_id = ? ORDER BY id", (lesson_id,)
        ).fetchall()
    return {
        **dict(lesson),
        "items": [dict(row) for row in items],
        "quiz_questions": [
            {**dict(row), "choices": json.loads(row["choices_json"])} for row in questions
        ],
    }


@app.put("/api/admin/lessons/{lesson_id}")
def admin_update_lesson(
    lesson_id: str, lesson: AdminLessonInput, admin: dict = Depends(get_admin_user)
) -> dict:
    accents = {"Vocabulary": "mint", "Travel": "peach", "Grammar": "lilac"}
    with database() as db:
        current = db.execute(
            "SELECT id FROM lessons WHERE id = ? AND owner_id IS NULL", (lesson_id,)
        ).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Shared lesson not found")
        ensure_course_is_unique(db, lesson, exclude_id=lesson_id)
        result = db.execute(
            """UPDATE lessons SET language = ?, title = ?, category = ?, level = ?,
            description = ?, accent = ? WHERE id = ? AND owner_id IS NULL""",
            (lesson.language, lesson.title.strip(), lesson.category, lesson.level,
             lesson.description.strip(), accents.get(lesson.category, "mint"), lesson_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Shared lesson not found")
        db.execute(
            "UPDATE quiz_questions SET language = ?, category = ?, level = ? WHERE lesson_id = ?",
            (lesson.language, lesson.category, lesson.level, lesson_id),
        )
        card_ids = db.execute(
            "SELECT id FROM lesson_items WHERE lesson_id = ?", (lesson_id,)
        ).fetchall()
        for card in card_ids:
            refresh_seed_questions_for_card(db, card["id"])
        row = db.execute(
            "SELECT * FROM lessons WHERE id = ?", (lesson_id,)
        ).fetchone()
    return dict(row)


@app.delete("/api/admin/lessons/{lesson_id}")
def admin_delete_lesson(lesson_id: str, admin: dict = Depends(get_admin_user)) -> dict:
    with database() as db:
        result = db.execute(
            "DELETE FROM lessons WHERE id = ? AND owner_id IS NULL", (lesson_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Shared lesson not found")
    return {"deleted": True}


@app.post("/api/admin/lessons/{lesson_id}/items", status_code=201)
def admin_add_card(
    lesson_id: str, item: CardInput, admin: dict = Depends(get_admin_user)
) -> dict:
    with database() as db:
        lesson = db.execute(
            "SELECT id FROM lessons WHERE id = ? AND owner_id IS NULL", (lesson_id,)
        ).fetchone()
        if lesson is None:
            raise HTTPException(status_code=404, detail="Shared lesson not found")
        cursor = db.execute(
            """INSERT INTO lesson_items
            (lesson_id, term, translation, pronunciation, example, example_translation)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (lesson_id, item.term.strip(), item.translation.strip(), item.pronunciation.strip(),
             item.example.strip(), item.example_translation.strip()),
        )
        seed_default_quiz_questions(db)
        return {"id": cursor.lastrowid, "saved": True}


@app.put("/api/admin/items/{item_id}")
def admin_update_card(
    item_id: int, item: CardInput, admin: dict = Depends(get_admin_user)
) -> dict:
    with database() as db:
        result = db.execute(
            """UPDATE lesson_items SET term = ?, translation = ?, pronunciation = ?,
            example = ?, example_translation = ? WHERE id = ? AND lesson_id IN
            (SELECT id FROM lessons WHERE owner_id IS NULL)""",
            (item.term.strip(), item.translation.strip(), item.pronunciation.strip(),
             item.example.strip(), item.example_translation.strip(), item_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Shared lesson card not found")
        refresh_seed_questions_for_card(db, item_id)
    return {"id": item_id, "saved": True}


@app.delete("/api/admin/items/{item_id}")
def admin_delete_card(item_id: int, admin: dict = Depends(get_admin_user)) -> dict:
    with database() as db:
        result = db.execute(
            """DELETE FROM lesson_items WHERE id = ? AND lesson_id IN
            (SELECT id FROM lessons WHERE owner_id IS NULL)""", (item_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Shared lesson card not found")
    return {"deleted": True}


@app.post("/api/admin/quiz-questions", status_code=201)
def admin_create_quiz_question(
    question: QuizQuestionInput, admin: dict = Depends(get_admin_user)
) -> dict:
    choices = list(dict.fromkeys(choice.strip() for choice in question.choices if choice.strip()))
    correct = question.correct_answer.strip()
    if len(choices) < 3 or correct not in choices:
        raise HTTPException(status_code=422, detail="Provide at least three unique choices including the correct answer")
    with database() as db:
        lesson = db.execute(
            "SELECT language, category FROM lessons WHERE id = ? AND owner_id IS NULL",
            (question.lesson_id,),
        ).fetchone()
        if lesson is None:
            raise HTTPException(status_code=404, detail="Shared lesson not found")
        cursor = db.execute(
            """INSERT INTO quiz_questions
            (lesson_id, language, category, level, question_type, prompt, choices_json,
             correct_answer, explanation, created_at)
            VALUES (?, ?, ?, ?, 'custom', ?, ?, ?, ?, ?)""",
            (question.lesson_id, lesson["language"], lesson["category"], question.level,
             question.prompt.strip(), json.dumps(choices, ensure_ascii=False), correct,
             question.explanation.strip(), datetime.now(timezone.utc).isoformat()),
        )
        return {"id": cursor.lastrowid, "saved": True}


@app.put("/api/admin/quiz-questions/{question_id}")
def admin_update_quiz_question(
    question_id: int, question: QuizQuestionInput, admin: dict = Depends(get_admin_user)
) -> dict:
    choices = list(dict.fromkeys(choice.strip() for choice in question.choices if choice.strip()))
    correct = question.correct_answer.strip()
    if len(choices) < 3 or correct not in choices:
        raise HTTPException(status_code=422, detail="Provide at least three unique choices including the correct answer")
    with database() as db:
        lesson = db.execute(
            "SELECT language, category FROM lessons WHERE id = ? AND owner_id IS NULL",
            (question.lesson_id,),
        ).fetchone()
        if lesson is None:
            raise HTTPException(status_code=404, detail="Shared lesson not found")
        result = db.execute(
            """UPDATE quiz_questions SET lesson_id = ?, language = ?, category = ?, level = ?,
            prompt = ?, choices_json = ?, correct_answer = ?, explanation = ?
            WHERE id = ? AND question_type = 'custom'""",
            (question.lesson_id, lesson["language"], lesson["category"], question.level,
             question.prompt.strip(), json.dumps(choices, ensure_ascii=False), correct,
             question.explanation.strip(), question_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Custom quiz question not found")
    return {"id": question_id, "saved": True}


@app.delete("/api/admin/quiz-questions/{question_id}")
def admin_delete_quiz_question(
    question_id: int, admin: dict = Depends(get_admin_user)
) -> dict:
    with database() as db:
        result = db.execute(
            "DELETE FROM quiz_questions WHERE id = ? AND question_type = 'custom'", (question_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Custom quiz question not found")
    return {"deleted": True}


@app.get("/api/quiz")
def start_quiz(
    language: str = "en",
    category: str = "All",
    level: str = "All",
    lesson_id: str | None = None,
    limit: int = 10,
    user: dict = Depends(get_current_user),
) -> dict:
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Language is not available")
    limit = max(1, min(limit, 20))
    with database() as db:
        rows = db.execute(
            """SELECT q.id, q.lesson_id, q.source_item_id, q.language, q.category, q.level,
            q.question_type, q.prompt, q.choices_json, l.title AS lesson_title
            FROM quiz_questions q JOIN lessons l ON l.id = q.lesson_id
            WHERE q.language = ? AND (? = 'All' OR q.category = ?)
              AND (? = 'All' OR q.level = ?)
              AND (? IS NULL OR q.lesson_id = ?)
              AND l.owner_id IS NULL
            ORDER BY RANDOM()""",
            (language, category, category, level, level, lesson_id, lesson_id),
        ).fetchall()
    questions = []
    seen_source_cards: set[int] = set()
    for row in rows:
        if row["source_item_id"] is not None:
            if row["source_item_id"] in seen_source_cards:
                continue
            seen_source_cards.add(row["source_item_id"])
        choices = json.loads(row["choices_json"])
        random.shuffle(choices)
        questions.append({
            "id": row["id"],
            "lesson_id": row["lesson_id"],
            "lesson_title": row["lesson_title"],
            "language": row["language"],
            "category": row["category"],
            "level": row["level"],
            "question_type": row["question_type"],
            "prompt": row["prompt"],
            "choices": choices,
        })
        if len(questions) >= limit:
            break
    if not questions:
        return {"session_id": None, "questions": []}

    session_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()
    # Reduced by 30% while keeping a little more time for harder levels and question types.
    seconds_by_level = {"Beginner": 21, "Intermediate": 32, "Advanced": 42}
    duration_seconds = sum(
        seconds_by_level.get(question["level"], 21)
        + (7 if question["question_type"] == "sentence" else 4 if question["question_type"] == "recall" else 0)
        for question in questions
    )
    deadline_at = (datetime.fromisoformat(started_at) + timedelta(seconds=duration_seconds)).isoformat()
    title = rows[0]["lesson_title"] if lesson_id else (
        f"{category} practice" if category != "All" else "Mixed practice"
    )
    with database() as db:
        db.execute(
            """INSERT INTO quiz_sessions
            (id, user_id, language, category, level, title, question_count, duration_seconds, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, user["id"], language, category, level, title, len(questions), duration_seconds, started_at),
        )
        db.executemany(
            "INSERT INTO quiz_session_questions (session_id, question_id, position) VALUES (?, ?, ?)",
            [(session_id, question["id"], position) for position, question in enumerate(questions)],
        )
    server_now = datetime.now(timezone.utc)
    remaining_seconds = max(0, (datetime.fromisoformat(deadline_at) - server_now).total_seconds())
    return {
        "session_id": session_id,
        "duration_seconds": duration_seconds,
        "remaining_seconds": remaining_seconds,
        "deadline_at": deadline_at,
        "server_now": server_now.isoformat(),
        "questions": questions,
    }


@app.post("/api/quiz/answer")
def answer_quiz_question(
    answer: QuizAnswer, user: dict = Depends(get_current_user)
) -> dict:
    with database() as db:
        session = db.execute(
            "SELECT * FROM quiz_sessions WHERE id = ? AND user_id = ?",
            (answer.session_id, user["id"]),
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Quiz session not found. Start a new quiz.")
        membership = db.execute(
            "SELECT 1 FROM quiz_session_questions WHERE session_id = ? AND question_id = ?",
            (answer.session_id, answer.question_id),
        ).fetchone()
        if membership is None:
            raise HTTPException(status_code=400, detail="This question does not belong to the current quiz.")
        question = db.execute(
            """SELECT q.id, q.correct_answer, q.explanation, q.lesson_id, l.owner_id
            FROM quiz_questions q JOIN lessons l ON l.id = q.lesson_id
            WHERE q.id = ? AND l.owner_id IS NULL""",
            (answer.question_id,),
        ).fetchone()
        if question is None:
            raise HTTPException(status_code=404, detail="Quiz question not found")
        previous_attempt = db.execute(
            "SELECT is_correct FROM quiz_attempts WHERE session_id = ? AND question_id = ?",
            (answer.session_id, answer.question_id),
        ).fetchone()
        timed_out = False
        if previous_attempt:
            correct = bool(previous_attempt["is_correct"])
        else:
            if session["completed_at"] is not None:
                raise HTTPException(status_code=409, detail="This quiz is already complete. Start another quiz.")
            deadline = datetime.fromisoformat(session["started_at"]) + timedelta(seconds=session["duration_seconds"])
            timed_out = datetime.now(timezone.utc) >= deadline
            correct = not timed_out and answer.answer.strip().casefold() == question["correct_answer"].strip().casefold()
            db.execute(
                """INSERT INTO quiz_attempts (question_id, user_id, session_id, is_correct, answered_at)
                VALUES (?, ?, ?, ?, ?)""",
                (question["id"], user["id"], answer.session_id, int(correct), datetime.now(timezone.utc).isoformat()),
            )
        result_row = db.execute(
            """SELECT COUNT(*) AS answered, COALESCE(SUM(is_correct), 0) AS correct
            FROM quiz_attempts WHERE session_id = ?""",
            (answer.session_id,),
        ).fetchone()
        session_result = None
        if session["completed_at"] is None and (
            timed_out or result_row["answered"] == session["question_count"]
        ):
            completed_at = datetime.now(timezone.utc).isoformat()
            score = (100 * result_row["correct"] + session["question_count"] // 2) // session["question_count"]
            db.execute(
                "UPDATE quiz_sessions SET correct_count = ?, score = ?, completed_at = ? WHERE id = ?",
                (result_row["correct"], score, completed_at, answer.session_id),
            )
            session_result = {
                "title": session["title"],
                "score": score,
                "correct_count": result_row["correct"],
                "question_count": session["question_count"],
                "completed_at": completed_at,
            }
        elif session["completed_at"] is not None:
            session_result = {
                "title": session["title"],
                "score": session["score"],
                "correct_count": session["correct_count"],
                "question_count": session["question_count"],
                "completed_at": session["completed_at"],
            }
        return {
            "correct": correct,
            "correct_answer": question["correct_answer"],
            "explanation": question["explanation"],
            "timed_out": timed_out,
            "session_result": session_result,
        }


@app.post("/api/quiz/expire")
def expire_quiz_session(
    request: QuizSessionAction, user: dict = Depends(get_current_user)
) -> dict:
    with database() as db:
        session = db.execute(
            "SELECT * FROM quiz_sessions WHERE id = ? AND user_id = ?",
            (request.session_id, user["id"]),
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Quiz session not found. Start a new quiz.")
        if session["completed_at"] is not None:
            return {
                "expired": True,
                "score": session["score"],
                "correct_count": session["correct_count"],
                "question_count": session["question_count"],
                "completed_at": session["completed_at"],
            }
        deadline = datetime.fromisoformat(session["started_at"]) + timedelta(seconds=session["duration_seconds"])
        now = datetime.now(timezone.utc)
        if now < deadline:
            remaining = max(1, int((deadline - now).total_seconds()))
            raise HTTPException(status_code=409, detail=f"This quiz still has {remaining} seconds remaining.")
        answered_at = now.isoformat()
        result = db.execute(
            "SELECT COALESCE(SUM(is_correct), 0) AS correct FROM quiz_attempts WHERE session_id = ?",
            (request.session_id,),
        ).fetchone()
        score = (100 * result["correct"] + session["question_count"] // 2) // session["question_count"]
        db.execute(
            "UPDATE quiz_sessions SET correct_count = ?, score = ?, completed_at = ? WHERE id = ?",
            (result["correct"], score, answered_at, request.session_id),
        )
        return {
            "expired": True,
            "score": score,
            "correct_count": result["correct"],
            "question_count": session["question_count"],
            "completed_at": answered_at,
        }


@app.get("/api/languages")
def list_languages(user: dict = Depends(get_current_user)) -> list[dict]:
    return list(LANGUAGES.values())


@app.get("/api/lessons")
def list_lessons(language: str = "en", user: dict = Depends(get_current_user)) -> list[dict]:
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Language is not available")
    with database() as db:
        rows = db.execute(
            """SELECT l.*, COUNT(DISTINCT i.id) AS item_count,
            COUNT(DISTINCT r.item_id) AS cards_studied,
            COALESCE(ROUND(100.0 * COUNT(DISTINCT r.item_id) / NULLIF(COUNT(DISTINCT i.id), 0)), 0) AS study_percent,
            COALESCE(qp.quiz_answers, 0) AS quiz_answers,
            COALESCE(qp.quiz_accuracy, 0) AS quiz_accuracy
            FROM lessons l LEFT JOIN lesson_items i ON i.lesson_id = l.id
            LEFT JOIN review_events r ON r.item_id = i.id AND r.user_id = ?
            LEFT JOIN (
                SELECT q.lesson_id, COUNT(*) AS quiz_answers,
                ROUND(100.0 * SUM(a.is_correct) / COUNT(*)) AS quiz_accuracy
                FROM quiz_attempts a JOIN quiz_questions q ON q.id = a.question_id
                WHERE a.user_id = ? GROUP BY q.lesson_id
            ) qp ON qp.lesson_id = l.id
            WHERE l.language = ? AND l.owner_id IS NULL
            GROUP BY l.id ORDER BY l.level, l.category, l.rowid""",
            (user["id"], user["id"], language),
        ).fetchall()
        return [dict(row) for row in rows]


@app.post("/api/lessons")
def deny_learner_lesson_creation(user: dict = Depends(get_current_user)) -> dict:
    raise HTTPException(status_code=403, detail="Learners cannot create lessons. Shared courses are managed by an administrator.")


@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: str, user: dict = Depends(get_current_user)) -> dict:
    with database() as db:
        lesson = db.execute(
            "SELECT * FROM lessons WHERE id = ? AND owner_id IS NULL",
            (lesson_id,),
        ).fetchone()
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found")
        items = db.execute(
            "SELECT * FROM lesson_items WHERE lesson_id = ? ORDER BY id", (lesson_id,)
        ).fetchall()
        return {**dict(lesson), "items": [dict(item) for item in items]}


@app.post("/api/lessons/{lesson_id}/items")
def deny_learner_card_creation(lesson_id: str, user: dict = Depends(get_current_user)) -> dict:
    raise HTTPException(status_code=403, detail="Learners cannot add lesson cards. Shared course content is managed by an administrator.")


@app.get("/api/progress")
def get_progress(
    language: str = "en",
    week_start: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Language is not available")
    today_date = date.today()
    current_week_start = today_date - timedelta(days=today_date.weekday())
    try:
        selected_week_start = date.fromisoformat(week_start) if week_start else current_week_start
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Week start must be a valid date in YYYY-MM-DD format") from error
    if selected_week_start.weekday() != 0:
        raise HTTPException(status_code=400, detail="Weeks must start on a Monday")
    if selected_week_start > current_week_start:
        raise HTTPException(status_code=400, detail="You cannot view a future week")
    selected_week_end = selected_week_start + timedelta(days=6)
    events_cte = """WITH events AS (
        SELECT r.id, r.user_id, r.is_correct, r.reviewed_at AS answered_at,
               l.id AS lesson_id, l.language
        FROM review_events r JOIN lesson_items i ON i.id = r.item_id
        JOIN lessons l ON l.id = i.lesson_id
        UNION ALL
        SELECT a.id, a.user_id, a.is_correct, a.answered_at,
               q.lesson_id, q.language
        FROM quiz_attempts a JOIN quiz_questions q ON q.id = a.question_id
    ) """
    with database() as db:
        summary = db.execute(
            events_cte + """SELECT COUNT(*) AS reviewed, COALESCE(SUM(is_correct), 0) AS correct
            FROM events WHERE user_id = ? AND language = ?""",
            (user["id"], language),
        ).fetchone()
        today = today_date.isoformat()
        focus_rows = db.execute(
            events_cte + """, per_lesson AS (
            SELECT lesson_id, COUNT(*) AS reviews, COALESCE(SUM(is_correct), 0) AS correct,
            SUM(CASE WHEN date(answered_at, 'localtime') = ? THEN 1 ELSE 0 END) AS today_reviews
            FROM events WHERE user_id = ? GROUP BY lesson_id
            ) SELECT l.id, l.title, l.description, l.category,
            COUNT(DISTINCT i.id) AS item_count, COALESCE(p.reviews, 0) AS reviews,
            COALESCE(p.correct, 0) AS correct, COALESCE(p.today_reviews, 0) AS today_reviews
            FROM lessons l
            LEFT JOIN lesson_items i ON i.lesson_id = l.id
            LEFT JOIN per_lesson p ON p.lesson_id = l.id
            WHERE l.language = ? AND l.owner_id IS NULL
            GROUP BY l.id ORDER BY l.owner_id IS NOT NULL, l.rowid""",
            (today, user["id"], language),
        ).fetchall()
        rows = db.execute(
            events_cte + """SELECT date(answered_at, 'localtime') AS day, COUNT(*) AS total,
            SUM(is_correct) AS correct FROM events
            WHERE user_id = ? AND language = ?
              AND date(answered_at, 'localtime') >= ? AND date(answered_at, 'localtime') <= ?
            GROUP BY date(answered_at, 'localtime') ORDER BY day""",
            (user["id"], language, selected_week_start.isoformat(), selected_week_end.isoformat()),
        ).fetchall()
        days = {row["day"]: dict(row) for row in rows}
        recent = []
        for offset in range(7):
            day = selected_week_start + timedelta(days=offset)
            recent.append({"date": day.isoformat(), **days.get(day.isoformat(), {"total": 0, "correct": 0})})
        quiz_rows = db.execute(
            """SELECT date(completed_at, 'localtime') AS day, COUNT(*) AS quiz_count,
            ROUND(AVG(score)) AS quiz_average
            FROM quiz_sessions
            WHERE user_id = ? AND language = ? AND completed_at IS NOT NULL
              AND date(completed_at, 'localtime') >= ? AND date(completed_at, 'localtime') <= ?
            GROUP BY date(completed_at, 'localtime') ORDER BY day""",
            (user["id"], language, selected_week_start.isoformat(), selected_week_end.isoformat()),
        ).fetchall()
        quiz_days = {row["day"]: dict(row) for row in quiz_rows}
        weekly_quizzes = []
        for offset in range(7):
            day = selected_week_start + timedelta(days=offset)
            result = quiz_days.get(day.isoformat())
            weekly_quizzes.append({
                "date": day.isoformat(),
                "quiz_count": result["quiz_count"] if result else 0,
                "quiz_average": result["quiz_average"] if result else None,
            })
        weekly_quiz_summary = db.execute(
            """SELECT COUNT(*) AS quiz_count, ROUND(AVG(score)) AS quiz_average
            FROM quiz_sessions
            WHERE user_id = ? AND language = ? AND completed_at IS NOT NULL
              AND date(completed_at, 'localtime') >= ? AND date(completed_at, 'localtime') <= ?""",
            (user["id"], language, selected_week_start.isoformat(), selected_week_end.isoformat()),
        ).fetchone()
        active_day_rows = db.execute(
            events_cte + """SELECT DISTINCT date(answered_at, 'localtime') AS day FROM events
            WHERE user_id = ? ORDER BY day DESC""",
            (user["id"],),
        ).fetchall()
        active_days = {row["day"] for row in active_day_rows}
        streak = 0
        cursor = today_date if today in active_days else today_date - timedelta(days=1)
        while cursor.isoformat() in active_days:
            streak += 1
            cursor -= timedelta(days=1)
        reviewed, correct = summary["reviewed"], summary["correct"]
        focus_options = [dict(row) for row in focus_rows]
        practiced = [lesson for lesson in focus_options if lesson["reviews"]]
        lessons_with_mistakes = [lesson for lesson in practiced if lesson["reviews"] > lesson["correct"]]
        if lessons_with_mistakes:
            focus = min(
                lessons_with_mistakes,
                key=lambda lesson: (
                    lesson["correct"] / lesson["reviews"],
                    -(lesson["reviews"] - lesson["correct"]),
                ),
            )
            focus_reason = "Picked from your past answers: this lesson could use a little more practice."
        elif focus_options:
            focus = min(
                focus_options,
                key=lambda lesson: (lesson["reviews"] / max(lesson["item_count"], 1), lesson["reviews"]),
            )
            focus_reason = "Chosen for your next step based on the lessons you have practised so far."
        else:
            focus = None
            focus_reason = "Choose a shared lesson to start your learning path."
        personalization = {
            "daily_goal": 5,
            "today_reviews": sum(lesson["today_reviews"] for lesson in focus_options),
            "focus_lesson": ({
                "id": focus["id"],
                "title": focus["title"],
                "category": focus["category"],
                "item_count": focus["item_count"],
                "reason": focus_reason,
            } if focus else None),
        }
        return {
            "reviewed": reviewed,
            "correct": correct,
            "accuracy": round((correct / reviewed) * 100) if reviewed else 0,
            "streak": streak,
            "streak_active_today": today in active_days,
            "weekly": recent,
            "weekly_quizzes": weekly_quizzes,
            "weekly_quiz_count": weekly_quiz_summary["quiz_count"],
            "weekly_quiz_average": weekly_quiz_summary["quiz_average"],
            "week_start": selected_week_start.isoformat(),
            "week_end": selected_week_end.isoformat(),
            "personalization": personalization,
        }


@app.post("/api/progress/reviews", status_code=201)
def save_review(review: ReviewSubmission, user: dict = Depends(get_current_user)) -> dict:
    with database() as db:
        item = db.execute(
            """SELECT i.id FROM lesson_items i JOIN lessons l ON l.id = i.lesson_id
            WHERE i.id = ? AND l.owner_id IS NULL""",
            (review.item_id,),
        ).fetchone()
        if item is None:
            raise HTTPException(status_code=404, detail="Learning card not found")
        result = db.execute(
            "INSERT INTO review_events (item_id, user_id, is_correct, reviewed_at) VALUES (?, ?, ?, ?)",
            (review.item_id, user["id"], int(review.correct), datetime.now(timezone.utc).isoformat()),
        )
        return {"id": result.lastrowid, "saved": True}


@app.get("/")
def home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/styles.css")
def frontend_styles() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "styles.css", media_type="text/css")


@app.get("/app.js")
def frontend_script() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "app.js", media_type="application/javascript")


app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
