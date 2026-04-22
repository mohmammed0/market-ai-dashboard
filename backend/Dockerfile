FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

ARG INSTALL_ML_DEPS=false

COPY backend/requirements-api.txt /app/backend/requirements-api.txt
COPY backend/requirements-ml.txt /app/backend/requirements-ml.txt

RUN pip install --upgrade pip && \
    pip install -r /app/backend/requirements-api.txt && \
    if [ "$INSTALL_ML_DEPS" = "true" ]; then pip install -r /app/backend/requirements-ml.txt; fi

COPY . /app
RUN mkdir -p /app/data /app/model_artifacts /app/seed_data/source_seed

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
