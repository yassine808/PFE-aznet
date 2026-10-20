# python:3.11-slim, pinned to digest (S8431 forbids tag+digest together)
FROM python@sha256:e748956ccf3f50c9555f236753bbcd5f430d3937e665d3bd6922dd0e6e591a24

WORKDIR /app

# psycopg2-binary ships a wheel, so no gcc/libpq-dev layer is needed.
# requirements.txt is fully pinned (==), so this install is reproducible.
COPY requirements.txt .
# Port 8000 and /app are both fine unprivileged: no <1024 bind, no root-owned
# write path.
RUN pip install --no-cache-dir --require-hashes --only-binary :all: -r requirements.txt \
    && groupadd -r appuser && useradd -r -g appuser appuser
COPY --chown=appuser:appuser app ./app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
