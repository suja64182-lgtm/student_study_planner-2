# Student Study Planner

A Flask planner for student accounts, subjects, study sessions, tasks, exams, and manual study plans. It stores real user data, enforces ownership on records, hashes passwords, and protects browser forms with CSRF tokens. AI is not required. In-app reminders are represented by upcoming due dates and exam dates on the dashboard; there is no background scheduler, email, or push delivery.

## Requirements

- Python 3.10+
- MySQL 8 for shared/production use (SQLite is the default for a quick local run and tests)

## Windows PowerShell setup (SQLite)

```powershell
cd 'C:\Users\CSE LAB-01-01\Downloads\student_study_planner'
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`, set `SECRET_KEY` to a long random value, and leave `DATABASE_URL` unset or set it to `sqlite:///study_planner.db` for local development. Initialize the schema and run:

```powershell
flask --app app init-db
python app.py
```

Open `http://127.0.0.1:5000`, register an account, and add subjects before scheduling sessions or exams.

## MySQL configuration

Create a database and a dedicated MySQL user with privileges on that database. `database/schema.sql` contains the non-destructive database creation starter; tables are created through SQLAlchemy. Set these values in `.env`:

```dotenv
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=mysql+pymysql://planner_user:your-password@127.0.0.1:3306/student_study_planner?charset=utf8mb4
FLASK_DEBUG=0
```

Then run `flask --app app init-db` and `python app.py`. URL-encode special characters in the database password. Never commit `.env`. To update an existing schema, use a deliberate migration process; `init-db` creates missing tables and does not drop existing data.

## Test

```powershell
python -m pytest -q
```

Tests use a fresh in-memory SQLite database. They do not connect to MySQL or use real student records.

## Features

- Student registration, login, logout, password hashing, and CSRF protection.
- Owner-scoped subjects, sessions, tasks, exams, study plans, and profile preferences.
- Session duration and time range validation with same-day overlap prevention.
- Task status changes, due dates, priorities, upcoming exams, and days remaining.
- Dashboard summaries calculated from stored records, with empty states.
- Responsive desktop sidebar and mobile navigation.

## Current limitations

- Study plans are manually managed date ranges and daily goals; there is no plan detail page or automatic session generation.
- Subject and exam records can be added and deleted; inline editing is not currently exposed.
- Reminders are visible in the app through dates, without scheduled background, email, or push notifications.
- Production deployment should use HTTPS and set `SESSION_COOKIE_SECURE=1`, use a production WSGI server, a strong secret, database migrations, and operational backups. The built-in Flask server is for development only.

