# SouthernProduce — ProducePricer

A full‑stack Flask web application for managing the costs and prices of produce, packaging, and raw materials. Built as a practical, production‑style project with authentication, data modeling, charting, AI summaries, CSV import/export, PDF parsing and automated tests.

This project demonstrates my ability to design and build a full-stack production-style application, from database design and authentication to testing and deployment. It highlights my interest in software engineering and applied AI.

---

## Table of contents

- Project overview
- Key features
- Architecture & technologies
- Installation (macOS)
- Configuration (.env)
- Database setup & migrations
- Running the app (development)
- Running tests
- Notes on design decisions & technical highlights
- Contribution & license

---

## Project overview

ProducePricer helps produce businesses track:
- Raw products, packaging, and items
- Historical costs and prices (with per‑entry timestamps)
- Cost calculations for items (raw materials, packaging, labor, designation)
- Charted trends (Chart.js)
- AI summaries for items / raw products / packaging (OpenAI)
- CSV import/export, PDF parsing for price lists
- Role‑aware flows (company admin, users)

---

## Key features

- Secure user authentication (Flask-Login, Bcrypt)
- Company‑scoped multi‑tenant data model
- CRUD for Items, Raw Products, Packaging, Customers, Price/Cost history
- Paginated lists (server‑side pagination for performance)
- Charts for cost/price trends (Chart.js)
- AI assisted summaries (OpenAI client wrapper)
- CSV import and PDF parsing (pdfplumber)
- Unit & functional tests (pytest)
- Email via Mailman (for user approvals / password resets)
- Database migrations via Flask‑Migrate (Alembic)

---

## Architecture & core libraries

- Framework: Flask (Blueprints)
- ORM: SQLAlchemy
- Forms: Flask‑WTF / WTForms
- Auth: Flask‑Login, password hashing with Flask‑Bcrypt
- Migrations: Flask‑Migrate (Alembic)
- Frontend: Bootstrap 4/5 (server‑rendered templates), Chart.js
- Async/External: OpenAI (via wrapper), pdfplumber (PDF text extraction), fpdf (PDF generation)
- Mail: flask-mailman
- Testing: pytest
- Deployment: Designed to run on a standard WSGI host (sqlite by default, configurable DB)

---

## Installation (macOS)

Prereqs: Python 3.10+ (deployed with 3.13.4), git, pip.

Open Terminal:

```bash
# clone
git clone https://github.com/CadeStocker/SouthernProduce.git SouthernProduce

# create virtualenv
python3 -m venv .venv
source .venv/bin/activate

# install
pip install -r requirements.txt
```

---

## Configuration (.env)

Create a `.env` in the project root (or set environment variables). Minimal set:

```env
SECRET_KEY=replace_with_secure_random
DATABASE_URL=sqlite:///instance/site.db   # optional, the app has defaults
EMAIL_USER=your-email@gmail.com
EMAIL_PASS=your-email-password
OPENAI_API_KEY=your-api-key
```

---

## Database & migrations

Initialize and migrate:

```bash
export FLASK_APP=producepricer
export FLASK_ENV=development

# create migrations folder (first time)
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

The application also supports an in‑memory SQLite DB for fast tests.

---

## Run (development)

Start the dev server:

```bash
# using the app factory default DB configured in create_app()
flask run --host=127.0.0.1 --port=5000
or
python run.py
# open http://127.0.0.1:5000
```
---

## Running tests

Tests use pytest. The test fixtures use an in‑memory SQLite DB and disable CSRF to simplify POSTs.

Run:

```bash
source .venv/bin/activate
pytest -q
```

Tips:
- Tests create/destroy DB schema per session; ensure `create_app()` supports a `db_uri` override.
- To debug failed tests, run a single test with `pytest tests/functional/test_raw_product.py::TestViewRawProduct::test_cost_history_chart -q -k <name>` or open the server and test manually.

---