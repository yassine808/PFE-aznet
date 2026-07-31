FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app

# psycopg2-binary ships a wheel, so no gcc/libpq-dev layer is needed.
# requirements.txt is fully pinned (==), so this install is reproducible.
COPY requirements.txt .
# Port 8000 and /app are both fine unprivileged: no <1024 bind, no root-owned
# write path.
RUN pip install --no-cache-dir --only-binary :all: -r requirements.txt \
    && groupadd -r appuser && useradd -r -g appuser appuser
COPY --chown=appuser:appuser app ./app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
