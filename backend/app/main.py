from __future__ import annotations

import hashlib
import hmac
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

app = FastAPI(title="Motiva Language Learning API", version="1.0.0")

LANGUAGES = {
    "en": {"code": "en", "name": "English", "flag": "🇬🇧"},
    "es": {"code": "es", "name": "Español", "flag": "🇪🇸"},
}

# Starter lessons are public examples. Users can create private lessons and cards.
STARTER_LESSONS = [
    {
        "id": "everyday-words", "language": "en", "title": "Everyday words",
        "category": "Vocabulary", "level": "Beginner",
        "description": "Useful words for daily conversations.", "accent": "mint",
        "items": [
            ("good morning", "bonjour", "/ɡʊd ˈmɔːrnɪŋ/", "Good morning, Emma!", "Bonjour, Emma !"),
            ("thank you", "merci", "/θæŋk juː/", "Thank you for your help.", "Merci pour ton aide."),
            ("please", "s’il vous plaît", "/pliːz/", "A glass of water, please.", "Un verre d’eau, s’il vous plaît."),
            ("today", "aujourd’hui", "/təˈdeɪ/", "Today is a good day.", "Aujourd’hui est une belle journée."),
            ("friend", "ami(e)", "/frend/", "She is my best friend.", "Elle est ma meilleure amie."),
        ],
    },
    {
        "id": "travel-essentials", "language": "en", "title": "Travel essentials",
        "category": "Travel", "level": "Beginner",
        "description": "Find your way and feel at home abroad.", "accent": "peach",
        "items": [
            ("Where is the station?", "Où est la gare ?", "/wer ɪz ðə ˈsteɪʃən/", "Excuse me, where is the station?", "Excusez-moi, où est la gare ?"),
            ("a ticket", "un billet", "/ə ˈtɪkɪt/", "I need a ticket to London.", "J’ai besoin d’un billet pour Londres."),
            ("left", "à gauche", "/left/", "Turn left at the next street.", "Tournez à gauche à la prochaine rue."),
            ("How much is it?", "Combien ça coûte ?", "/haʊ mʌtʃ ɪz ɪt/", "How much is it, please?", "Combien ça coûte, s’il vous plaît ?"),
            ("I need help", "J’ai besoin d’aide", "/aɪ niːd help/", "I need help with my bag.", "J’ai besoin d’aide avec mon sac."),
        ],
    },
    {
        "id": "grammar-basics", "language": "en", "title": "Grammar basics",
        "category": "Grammar", "level": "Beginner",
        "description": "Build simple sentences with confidence.", "accent": "lilac",
        "items": [
            ("I am learning", "J’apprends", "/aɪ æm ˈlɜːrnɪŋ/", "I am learning English.", "J’apprends l’anglais."),
            ("I would like…", "Je voudrais…", "/aɪ wʊd laɪk/", "I would like a coffee.", "Je voudrais un café."),
            ("Do you speak French?", "Parlez-vous français ?", "/duː juː spiːk frentʃ/", "Do you speak French or English?", "Parlez-vous français ou anglais ?"),
            ("I have", "J’ai", "/aɪ hæv/", "I have a question.", "J’ai une question."),
            ("Can you help me?", "Pouvez-vous m’aider ?", "/kæn juː help miː/", "Can you help me, please?", "Pouvez-vous m’aider, s’il vous plaît ?"),
        ],
    },
    {
        "id": "es-everyday-words", "language": "es", "title": "Palabras de cada día",
        "category": "Vocabulary", "level": "Beginner",
        "description": "Vocabulaire essentiel pour les conversations du quotidien.", "accent": "mint",
        "items": [
            ("hola", "bonjour / salut", "/ˈo.la/", "Hola, ¿cómo estás?", "Salut, comment vas-tu ?"),
            ("gracias", "merci", "/ˈɡɾa.sjas/", "Muchas gracias por tu ayuda.", "Merci beaucoup pour ton aide."),
            ("por favor", "s’il vous plaît", "/poɾ faˈβoɾ/", "Un café, por favor.", "Un café, s’il vous plaît."),
            ("hoy", "aujourd’hui", "/oi/", "Hoy hace buen tiempo.", "Il fait beau aujourd’hui."),
            ("amigo / amiga", "ami / amie", "/aˈmi.ɣo/", "Ella es mi mejor amiga.", "Elle est ma meilleure amie."),
        ],
    },
    {
        "id": "es-travel-essentials", "language": "es", "title": "Viajar con confianza",
        "category": "Travel", "level": "Beginner",
        "description": "Les phrases utiles pour se déplacer et demander de l’aide.", "accent": "peach",
        "items": [
            ("¿Dónde está la estación?", "Où est la gare ?", "/ˈdon.de esˈta la es.taˈsjon/", "Perdón, ¿dónde está la estación?", "Excusez-moi, où est la gare ?"),
            ("un billete", "un billet", "/un biˈʝe.te/", "Necesito un billete para Madrid.", "J’ai besoin d’un billet pour Madrid."),
            ("a la izquierda", "à gauche", "/a la isˈkjeɾ.ða/", "Gira a la izquierda aquí.", "Tourne à gauche ici."),
            ("¿Cuánto cuesta?", "Combien ça coûte ?", "/ˈkwan.to ˈkwes.ta/", "¿Cuánto cuesta, por favor?", "Combien ça coûte, s’il vous plaît ?"),
            ("Necesito ayuda", "J’ai besoin d’aide", "/ne.seˈsi.to aˈʝu.ða/", "Necesito ayuda con mi maleta.", "J’ai besoin d’aide avec ma valise."),
        ],
    },
    {
        "id": "es-grammar-basics", "language": "es", "title": "Gramática esencial",
        "category": "Grammar", "level": "Beginner",
        "description": "Construire ses premières phrases en espagnol.", "accent": "lilac",
        "items": [
            ("Estoy aprendiendo", "J’apprends", "/esˈtoj a.pɾenˈdjen.do/", "Estoy aprendiendo español.", "J’apprends l’espagnol."),
            ("Quisiera…", "Je voudrais…", "/kiˈsje.ɾa/", "Quisiera un café.", "Je voudrais un café."),
            ("¿Hablas francés?", "Parles-tu français ?", "/ˈa.βlas fɾanˈses/", "¿Hablas francés o inglés?", "Parles-tu français ou anglais ?"),
            ("Tengo", "J’ai", "/ˈteŋ.ɡo/", "Tengo una pregunta.", "J’ai une question."),
            ("¿Puedes ayudarme?", "Peux-tu m’aider ?", "/ˈpwe.ðes a.ʝuˈðaɾ.me/", "¿Puedes ayudarme, por favor?", "Peux-tu m’aider, s’il te plaît ?"),
        ],
    },
]


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
                created_at TEXT NOT NULL
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
            """
        )
        lesson_columns = {row["name"] for row in db.execute("PRAGMA table_info(lessons)")}
        if "language" not in lesson_columns:
            db.execute("ALTER TABLE lessons ADD COLUMN language TEXT NOT NULL DEFAULT 'en'")
        if "owner_id" not in lesson_columns:
            db.execute("ALTER TABLE lessons ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        review_columns = {row["name"] for row in db.execute("PRAGMA table_info(review_events)")}
        if "user_id" not in review_columns:
            db.execute("ALTER TABLE review_events ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")

        for lesson in STARTER_LESSONS:
            db.execute(
                "INSERT OR IGNORE INTO lessons "
                "(id, language, title, category, level, description, accent, owner_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                tuple(lesson[key] for key in ("id", "language", "title", "category", "level", "description", "accent")),
            )
            count = db.execute(
                "SELECT COUNT(*) FROM lesson_items WHERE lesson_id = ?", (lesson["id"],)
            ).fetchone()[0]
            if count == 0:
                db.executemany(
                    """INSERT INTO lesson_items
                    (lesson_id, term, translation, pronunciation, example, example_translation)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    [(lesson["id"], *item) for item in lesson["items"]],
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
            """SELECT u.id, u.username FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > ?""",
            (token_digest(token), datetime.now(timezone.utc).isoformat()),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again")
    return dict(row)


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=24, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class LessonInput(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    language: Literal["en", "es"]
    category: Literal["Vocabulary", "Travel", "Grammar"]
    description: str = Field(min_length=3, max_length=180)


class CardInput(BaseModel):
    term: str = Field(min_length=1, max_length=160)
    translation: str = Field(min_length=1, max_length=160)
    pronunciation: str = Field(min_length=1, max_length=100)
    example: str = Field(min_length=1, max_length=220)
    example_translation: str = Field(min_length=1, max_length=220)


class ReviewSubmission(BaseModel):
    item_id: int = Field(gt=0)
    correct: bool


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
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, hash_password(credentials.password), datetime.now(timezone.utc).isoformat()),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="That username is already taken") from error
    create_session(response, user_id)
    return {"id": user_id, "username": username}


@app.post("/api/auth/login")
def login(credentials: Credentials, response: Response) -> dict:
    with database() as db:
        user = db.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ? COLLATE NOCASE",
            (credentials.username.strip(),),
        ).fetchone()
    if user is None or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Username or password is incorrect")
    create_session(response, user["id"])
    return {"id": user["id"], "username": user["username"]}


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


@app.get("/api/languages")
def list_languages(user: dict = Depends(get_current_user)) -> list[dict]:
    return list(LANGUAGES.values())


@app.get("/api/lessons")
def list_lessons(language: str = "en", user: dict = Depends(get_current_user)) -> list[dict]:
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Language is not available")
    with database() as db:
        rows = db.execute(
            """SELECT l.*, COUNT(i.id) AS item_count
            FROM lessons l LEFT JOIN lesson_items i ON i.lesson_id = l.id
            WHERE l.language = ? AND (l.owner_id IS NULL OR l.owner_id = ?)
            GROUP BY l.id ORDER BY l.owner_id IS NOT NULL, l.rowid""",
            (language, user["id"]),
        ).fetchall()
        return [dict(row) for row in rows]


@app.post("/api/lessons", status_code=201)
def create_lesson(lesson: LessonInput, user: dict = Depends(get_current_user)) -> dict:
    lesson_id = f"user-{user['id']}-{uuid.uuid4().hex}"
    with database() as db:
        db.execute(
            """INSERT INTO lessons (id, language, title, category, level, description, accent, owner_id)
            VALUES (?, ?, ?, ?, 'Beginner', ?, ?, ?)""",
            (lesson_id, lesson.language, lesson.title.strip(), lesson.category,
             lesson.description.strip(), {"Vocabulary": "mint", "Travel": "peach", "Grammar": "lilac"}[lesson.category], user["id"]),
        )
        row = db.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        return {**dict(row), "item_count": 0}


@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: str, user: dict = Depends(get_current_user)) -> dict:
    with database() as db:
        lesson = db.execute(
            "SELECT * FROM lessons WHERE id = ? AND (owner_id IS NULL OR owner_id = ?)",
            (lesson_id, user["id"]),
        ).fetchone()
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found")
        items = db.execute(
            "SELECT * FROM lesson_items WHERE lesson_id = ? ORDER BY id", (lesson_id,)
        ).fetchall()
        return {**dict(lesson), "items": [dict(item) for item in items]}


@app.post("/api/lessons/{lesson_id}/items", status_code=201)
def add_lesson_item(lesson_id: str, item: CardInput, user: dict = Depends(get_current_user)) -> dict:
    with database() as db:
        lesson = db.execute(
            "SELECT id FROM lessons WHERE id = ? AND owner_id = ?", (lesson_id, user["id"])
        ).fetchone()
        if lesson is None:
            raise HTTPException(status_code=404, detail="Your lesson was not found")
        cursor = db.execute(
            """INSERT INTO lesson_items
            (lesson_id, term, translation, pronunciation, example, example_translation)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (lesson_id, item.term.strip(), item.translation.strip(), item.pronunciation.strip(),
             item.example.strip(), item.example_translation.strip()),
        )
        return {"id": cursor.lastrowid, "saved": True}


@app.get("/api/progress")
def get_progress(language: str = "en", user: dict = Depends(get_current_user)) -> dict:
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Language is not available")
    with database() as db:
        summary = db.execute(
            """SELECT COUNT(*) AS reviewed, COALESCE(SUM(r.is_correct), 0) AS correct
            FROM review_events r JOIN lesson_items i ON i.id = r.item_id
            JOIN lessons l ON l.id = i.lesson_id
            WHERE r.user_id = ? AND l.language = ?""",
            (user["id"], language),
        ).fetchone()
        today = date.today().isoformat()
        focus_rows = db.execute(
            """SELECT l.id, l.title, l.description, l.category,
            COUNT(DISTINCT i.id) AS item_count, COUNT(r.id) AS reviews,
            COALESCE(SUM(r.is_correct), 0) AS correct,
            COALESCE(SUM(CASE WHEN date(r.reviewed_at) = ? THEN 1 ELSE 0 END), 0) AS today_reviews
            FROM lessons l
            LEFT JOIN lesson_items i ON i.lesson_id = l.id
            LEFT JOIN review_events r ON r.item_id = i.id AND r.user_id = ?
            WHERE l.language = ? AND (l.owner_id IS NULL OR l.owner_id = ?)
            GROUP BY l.id ORDER BY l.owner_id IS NOT NULL, l.rowid""",
            (today, user["id"], language, user["id"]),
        ).fetchall()
        rows = db.execute(
            """SELECT date(r.reviewed_at) AS day, COUNT(*) AS total,
            SUM(r.is_correct) AS correct FROM review_events r
            JOIN lesson_items i ON i.id = r.item_id JOIN lessons l ON l.id = i.lesson_id
            WHERE r.user_id = ? AND l.language = ? AND r.reviewed_at >= ?
            GROUP BY date(r.reviewed_at) ORDER BY day""",
            (user["id"], language, (date.today() - timedelta(days=6)).isoformat()),
        ).fetchall()
        days = {row["day"]: dict(row) for row in rows}
        recent = []
        for offset in range(6, -1, -1):
            day = date.today() - timedelta(days=offset)
            recent.append({"date": day.isoformat(), **days.get(day.isoformat(), {"total": 0, "correct": 0})})
        streak = 0
        cursor = date.today()
        while cursor.isoformat() in days:
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
            focus_reason = "Create a lesson to start your personal learning path."
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
            "weekly": recent,
            "personalization": personalization,
        }


@app.post("/api/progress/reviews", status_code=201)
def save_review(review: ReviewSubmission, user: dict = Depends(get_current_user)) -> dict:
    with database() as db:
        item = db.execute(
            """SELECT i.id FROM lesson_items i JOIN lessons l ON l.id = i.lesson_id
            WHERE i.id = ? AND (l.owner_id IS NULL OR l.owner_id = ?)""",
            (review.item_id, user["id"]),
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
