# Etic'Monts — application image (Flask + Gunicorn)
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY app.py ./
COPY deploy/gunicorn.conf.py deploy/gunicorn.conf.py
COPY eticmonts/ eticmonts/
COPY templates/ templates/
COPY static/ static/
COPY scripts/seed_demo.py scripts/seed_demo.py

# Non-root user with the usual host UID so bind-mounted uploads stay writable.
RUN adduser --disabled-password --no-create-home --uid 1000 appuser && \
    mkdir -p /app/static/uploads/profile && \
    chown -R appuser:appuser /app/static/uploads
USER appuser

EXPOSE 8000

CMD ["gunicorn", "-c", "deploy/gunicorn.conf.py", "app:app"]
