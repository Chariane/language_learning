# Motiva — Language Learning App

Motiva is a web app for learning English or Spanish with French translations. It includes themed lessons, flashcards, pronunciation guides, a quiz, and saved learning progress.

## Requirements

- Python 3.10 or newer
- pip

## Run the app

From this folder, create and activate a virtual environment, then install the backend requirements:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload
```

Open <http://127.0.0.1:8000> in Chrome. The FastAPI backend serves the web interface and its API. SQLite creates `data/motiva.db` automatically and keeps progress between launches.

## Features

- Choose English or Spanish as the language to learn
- Lessons grouped by vocabulary, travel, and grammar
- Flashcards with translations, IPA guides, spoken pronunciation, and examples
- A multiple-choice quiz with immediate feedback
- A dashboard with review count, accuracy, and recent progress
- A FastAPI REST API backed by SQLite

The sample course content covers beginner English and Spanish with French translations. Quiz progress is stored on the computer running the backend in SQLite. The app does not include user accounts or cloud synchronization.
