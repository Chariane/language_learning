# Motiva — Language Learning App

Motiva is a web app for learning English or Spanish with French translations. Learners can study lessons, practise with flashcards, take quizzes, and follow progress saved to their account. Administrators manage the shared course library and quiz bank from the Admin studio.

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

Open <http://127.0.0.1:8000> in Chrome. Keep the terminal running while using the app. Open the FastAPI address instead of `frontend/index.html` directly so the API and frontend load from the same server.

## Create an administrator account

Set these environment variables in the terminal **before** starting FastAPI. Pick your own username and password:

```bash
export MOTIVA_ADMIN_USERNAME=your_username
export MOTIVA_ADMIN_PASSWORD='choose-a-password-with-at-least-8-characters'
uvicorn backend.app.main:app --reload
```

The first startup creates this account with the administrator role. If that username already exists, startup grants it the administrator role; its existing password stays the same. Sign in with that account and choose **Admin studio** in the sidebar. New accounts created through the sign-up page are learners and cannot open the studio.

To make the administrator role available after restarting the server, keep the two variables set in the terminal session used to run FastAPI. Do not commit real credentials to the project.

## Features

### Learners

- Create an account and sign in with a username and password
- Choose English or Spanish, with French translations
- Study vocabulary, travel, and grammar lessons
- Practise with flashcards, pronunciation guides, spoken audio, and examples; rate each revealed card as known or needing more practice
- Take random multiple-choice quizzes filtered by category and difficulty, with a time limit that adapts to question difficulty and type
- Get immediate answer feedback, explanations, a final mark, and a review of missed questions
- See review totals, accuracy, streaks, weekly activity, and a personal lesson recommendation
- Review Monday-to-Sunday activity and quiz results, with controls to browse past weeks and return to the current week
- Build a current-day streak through either a saved flashcard review or a submitted quiz answer
- Track flashcards studied and quiz attempts/accuracy for each course
- Choose, replace, or remove a profile photo from the device (PNG, JPEG, or WebP up to 2 MB)
- Browse courses grouped and filterable by Beginner, Intermediate, and Advanced level
- Switch between light and dark mode; the selection is remembered in the browser
- Learner accounts can study shared lessons but cannot create or edit lessons or cards

### Administrators

- View shared lesson, card, quiz-question, and answer totals
- Create and edit shared lessons by language, category, and difficulty
- Add, edit, and delete lesson cards
- Add, edit, and delete custom quiz questions with 3–4 choices, a correct answer, and an explanation
- Read the full content of each course and quiz, including card examples, every answer choice, the correct answer, and its explanation
- Edit auto-generated quiz questions through their source flashcards; custom quiz questions can be edited or deleted directly
- Review the generated question bank for each shared lesson
- Delete a shared lesson and its associated cards and questions
- Review each learner's course activity, flashcard coverage, quiz answers, and accuracy

## Courses, quizzes, and saved data

FastAPI serves the frontend and provides the API. SQLite stores user accounts, profile photos, lessons, cards, quiz questions, quiz sessions, and learner answers in `data/motiva.db`.

The prebuilt shared courses and their starter cards are in `backend/app/seed_lessons.json`, with English and Spanish courses at Beginner, Intermediate, and Advanced levels across vocabulary, travel, and grammar. At startup, the backend adds any missing starter course to SQLite without overwriting administrator edits or learner activity. Course identity is checked by language, normalized title, category, and level, so repeated seed entries and duplicate admin submissions are rejected. Administrators can extend or edit the shared course library in the Admin studio; those changes are saved in the same database. Learner accounts can read and study shared courses; lesson creation and editing are restricted to administrators in both the interface and API.

Quiz questions are stored in the `quiz_questions` table. The app creates multiple-choice word, recall, and sentence questions from lesson cards and stores them alongside questions written by administrators. Starting a quiz creates a user-specific record in `quiz_sessions` and records its question set. Its time limit is calculated from the actual selected questions: Beginner questions get 21 seconds, Intermediate 32 seconds, and Advanced 42 seconds, with 4 extra seconds for recall and 7 for sentence questions. These limits are 30% shorter than the previous settings. A visible countdown uses a monotonic browser timer initialized with the server-reported remaining time, so changes to the computer clock do not distort it; the server remains authoritative and enforces the deadline. When time expires, unanswered questions count as incorrect in the final mark, while only answers actually submitted are stored in `quiz_attempts`. The final mark and completion time are saved. The weekly dashboard uses completed sessions to show each day's average mark and the week's average; unfinished quizzes do not count as a final result. Weeks run Monday through Sunday. Learners can browse past weeks and move forward only as far as the current week. The weekly score chart starts with quizzes completed after this update; older individual answers cannot be reliably combined into past quiz scores.

When a learner reveals a flashcard, they can mark it as known or needing more practice. That choice is saved as a user-specific review event. Course cards show the number and percentage of distinct cards studied, plus quiz answers and accuracy. Quiz answers are associated with their source course. The Admin studio can inspect these measures per learner. Courses are grouped by level and can also be filtered by category.

The dashboard counts saved flashcard reviews and quiz answers; its weekly quiz chart shows only fully completed quizzes. The streak is based on distinct active dates in the server's local timezone. If the learner has not practised today, activity from yesterday keeps the current streak active until the end of today. A second full day without activity resets it to zero. Profile photos are converted to a validated image data URL and stored on the user's SQLite account record, so they persist across sessions and browser restarts. Users and administrators can choose, replace, or delete their own photo.

The SQLite file is local to the computer running FastAPI. Back up `data/motiva.db` to preserve accounts and app data. Passwords are stored as PBKDF2 hashes, and sessions use HttpOnly cookies. This project does not include cloud hosting or account recovery. For an HTTPS deployment, configure secure cookies and serve the app over HTTPS.

## Project structure

```text
backend/app/main.py         FastAPI routes, authentication, and SQLite access
backend/app/seed_lessons.json Prebuilt lesson and flashcard content
frontend/index.html         Web app structure, including the Admin studio
frontend/styles.css         Responsive light and dark themes
frontend/app.js             Frontend behavior and API calls
data/motiva.db              SQLite database, created automatically
```
