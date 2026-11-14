FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# rasterio's bundled GDAL needs libexpat, which python:slim omits (found when Phase 3 imported rasterio at startup).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home appuser

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt

COPY . .
USER appuser
EXPOSE 8000

# Run migrations, then start the API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
