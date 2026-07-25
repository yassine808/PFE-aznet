FROM python:3.11-slim

WORKDIR /app

# psycopg2-binary ships a wheel, so no gcc/libpq-dev layer is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
