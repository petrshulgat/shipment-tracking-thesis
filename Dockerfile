# One image for all Python services (API now; ETL scheduler later).
# Each service picks what to run with `command:` in docker-compose.yml.
FROM python:3.14-slim

WORKDIR /code

# Install dependencies first so Docker caches this layer when only code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY generator ./generator
