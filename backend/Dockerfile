FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt

RUN pip install --upgrade pip && \
    pip install -r /app/backend/requirements.txt

COPY . /app
RUN mkdir -p /app/data /app/model_artifacts /app/seed_data/source_seed

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
