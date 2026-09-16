# Vakola Jumma Masjid — Flask site

Production Flask rewrite of the original Figma Make / React prototype. Same
design, now backed by a real database, live daily prayer times, and working
forms instead of static mock data.

## What changed from the React prototype

- **Prayer times are real**, not hardcoded — fetched daily from the
  [Aladhan API](https://aladhan.com/prayer-times-api) for the mosque's
  coordinates, cached server-side, with Iqama times computed from
  configurable per-prayer offsets stored in the database.
- **Nikah / Madrasa / Donation forms actually submit** to the backend,
  are validated server-side, and are persisted (`NikahApplication`,
  `MadrasaApplication`, `Donation`).
- **Donations** integrate with Razorpay when configured (`RAZORPAY_KEY_ID`
  / `RAZORPAY_KEY_SECRET`); with no keys set, donations are recorded as a
  "pledge" for manual follow-up instead of silently doing nothing.
- **Jumu'ah collection figures** are computed from real `JummaCollection`
  rows instead of hardcoded strings.
- CSRF protection, rate limiting, security headers, structured logging,
  health check endpoint, and a Postgres-backed schema with migrations.

## Stack

Flask 3 · SQLAlchemy · Flask-Migrate · Flask-WTF (CSRF) · Flask-Limiter ·
PostgreSQL (Neon-compatible) · Jinja2 · Tailwind CSS (CLI build, no CDN) ·
vanilla JS · Gunicorn.

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

npm install
npm run build:css        # or: npm run watch:css while developing

cp .env.example .env     # fill in SECRET_KEY, DATABASE_URL, etc.
```

For local dev without Neon, leave `DATABASE_URL` blank — it falls back to
a local SQLite file at `instance/dev.db`.

```bash
export FLASK_ENV=development   # or set it in .env
flask --app run.py db init
flask --app run.py db migrate -m "initial schema"
flask --app run.py db upgrade
flask --app run.py seed        # default Iqama offsets + sample notices

python run.py                  # http://localhost:5000
```

## Database migrations (Neon / production)

```bash
export DATABASE_URL="postgresql://user:pass@ep-xxxx.neon.tech/dbname?sslmode=require"
flask --app wsgi.py db upgrade
flask --app wsgi.py seed
```

Run `flask --app wsgi.py db migrate -m "message"` whenever you change
`app/models.py`, then `db upgrade` to apply it.

## Running in production

```bash
docker compose up --build          # local Postgres + app, for a full smoke test
```

or on your own infrastructure:

```bash
npm ci && npm run build:css        # produces app/static/css/tailwind.css
pip install -r requirements.txt
gunicorn -c gunicorn.conf.py wsgi:app
```

Required environment variables in production: `SECRET_KEY`,
`DATABASE_URL`. Everything else has a sane default (see `.env.example`).
`GET /healthz` returns `200` when the app and database are reachable —
point your load balancer / orchestrator health check at it.

## Adding real content

- **Iqama offsets**: edit rows in `iqama_settings` (seeded by `flask seed`)
  or extend `app/seed.py`. There's no admin UI yet — this is the natural
  next feature to add (a small `/admin` blueprint behind auth).
- **Announcements**: add rows to `announcements`.
- **Weekly Jumu'ah collection**: add a row to `jumma_collections` each
  Friday (`collection_date`, `amount`). "This week / last week / this
  month" and the goal progress bar are all computed from this table.

## Project layout

```
app/
  __init__.py        app factory, error handlers, security headers, CLI
  extensions.py       db / migrate / csrf / limiter singletons
  models.py            SQLAlchemy models
  seed.py              flask seed CLI command
  services/
    prayer_times.py   Aladhan integration + Iqama calculation
  routes/
    main.py           page rendering + jumma stats
    api.py             /api/nikah, /api/madrasa, /api/donate(+/verify)
  templates/            Jinja2, ported 1:1 from the original design
  static/
    css/input.css      Tailwind source (build with `npm run build:css`)
    js/main.js          clock, modals, form + donation JS
config.py               environment-based config classes
run.py / wsgi.py         dev / production entry points
gunicorn.conf.py
Dockerfile / docker-compose.yml
```
