# python:3.11-slim, pinned to digest (S8431 forbids tag+digest together)
FROM python@sha256:b0aed0e0059e9b1527ef57689a7206f32526627b0713e2228a916df62880188a

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
