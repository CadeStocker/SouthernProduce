# SouthernProduce — ProducePricer

A full‑stack Flask web application for managing the costs and prices of produce, packaging, and raw materials. Built as a practical, production‑style project with authentication, data modeling, charting, AI summaries, CSV import/export, PDF parsing and automated tests.

This project demonstrates my ability to design and build a full-stack production-style application, from database design and authentication to testing and deployment. It highlights my interest in software engineering and applied AI.

This project was created for Southern Produce Processors Inc.
https://mysouthernproduce.com/

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

This project shows full‑stack skills: REST endpoints, server‑side rendering, database modeling, asynchronous considerations for heavy workloads, and test automation.

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

Prereqs: Python 3.10+ (3.11.10 recommended), git, pip.

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

The app factory accepts an explicit `db_uri` for testing (useful for CI).

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

When working on templates, refresh the browser for changes. For Chart.js charts and CSV uploads, verify static files are served and correct CDN links are present.

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

## Notes on design decisions & technical highlights

- Multi‑tenant model: all models carry `company_id` to scope data to an organization — important for real business use cases and security.
- Pagination: server‑side pagination used on listing pages to avoid loading large datasets and to enable stable URLable pages for sharing and testing.
- Forms: WTForms select fields are populated before validation so tests and POSTs validate correctly. Tests illustrate typical pitfalls (CSRF in tests, session detached objects).
- Tests: Functional tests use Flask test client and app factory pattern, demonstrating maintainable testing practices.
- AI integration: lightweight wrapper around OpenAI for summarization tasks, with responses persisted (AIResponse model) for audit/history.
- Charting & UX: Chart.js used for interactive client‑side graphs fed by server JSON/templated arrays.
- Robust PDF handling: pdfplumber is used with careful exception handling; backend uses 'Agg' matplotlib for headless charting if required.
---

## Troubleshooting / common issues

- "Cannot nest client invocations" in tests: avoid nested `with client:` usage; log in using `client.post(...)` outside a context manager.
- DetachedInstanceError: return only IDs from fixtures or requery objects inside an app context.
- Missing pagination Location header in tests: ensure form choices are populated before `validate_on_submit()` so SelectField can validate.
- CSRF in tests: disable `WTF_CSRF_ENABLED` in test config OR include the token in form posts.

---

## Contributing

- Fork, branch per feature/fix, create tests for new behavior, open a PR.
- Follow the code style in the repo; tests should pass locally before opening a PR.

---

## License

Include your chosen license (e.g. MIT) or state "All rights reserved" depending on intended use.

---

## Contact / portfolio note

This project demonstrates end‑to‑end software engineering: UX for business users, robust server logic, database design, third‑party API integration, and automated tests — a strong example for graduate applications focusing on systems, software engineering, or data‑driven applications.

Deployed at: https://producepricer.onrender.com

