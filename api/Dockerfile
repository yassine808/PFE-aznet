FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6

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
