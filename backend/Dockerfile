# Submission requires a containerized app — build this from day one, not at the end.
FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY demo ./demo

EXPOSE 8080

# Secrets are passed at runtime (docker run -e ...), never baked into the image.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
