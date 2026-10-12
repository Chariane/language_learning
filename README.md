# Motiva — Language Learning App

Motiva is a web app for learning English or Spanish with French translations. Learners can study lessons, practise with flashcards, take quizzes, and follow progress saved to their own account.

## Requirements

- Python 3.10 or newer
- `pip`

## Run the app

From the project root, create and activate a virtual environment, install the dependencies, and start FastAPI:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload
```

Open <http://127.0.0.1:8000> in Chrome. Keep the terminal running while you use the app. Open the FastAPI address rather than `frontend/index.html` directly so the API, styles, and JavaScript all load from the same server.

## Features

- Create an account and sign in with a username and password
- Choose English or Spanish, with French translations
- Study vocabulary, travel, and grammar lessons
- Use flashcards with translations, pronunciation guides, spoken audio, and examples
- Create private lessons and add your own cards
- Take multiple-choice quizzes, see a live score, receive a final percentage and letter grade, and review missed answers
- See review totals, accuracy, streaks, and weekly activity on the dashboard
- Get a personal lesson recommendation based on your quiz answers and a daily goal of five reviews

## Data and accounts

FastAPI serves the frontend and provides the API. SQLite stores data in `data/motiva.db`. Accounts, private lessons, and quiz progress are kept between launches and separated by user. The daily recommendation uses the signed-in user's own quiz history; starter lessons are shared examples.

Passwords are stored as PBKDF2 hashes, and login sessions use HttpOnly cookies. This project stores data on the computer running the backend; it does not include cloud hosting or account recovery. The cookie is configured for local development. For an HTTPS deployment, enable secure cookies and serve the app over HTTPS.

## Project structure

```text
backend/app/main.py   FastAPI routes, authentication, and SQLite access
frontend/index.html   Web app structure
frontend/styles.css   App styles
frontend/app.js       Frontend behavior
data/motiva.db       SQLite database, created automatically
```
