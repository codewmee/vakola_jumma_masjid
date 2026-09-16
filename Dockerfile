FROM node:20-slim AS assets
WORKDIR /build
COPY package.json tailwind.config.js ./
RUN npm install
COPY app/templates ./app/templates
COPY app/static/css/input.css ./app/static/css/input.css
COPY app/static/js ./app/static/js
RUN npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/tailwind.css --minify

FROM python:3.12-slim
WORKDIR /srv/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=assets /build/app/static/css/tailwind.css ./app/static/css/tailwind.css

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
