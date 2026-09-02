FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements-runtime.lock alembic.ini ./
RUN pip install --upgrade pip && pip install -r requirements-runtime.lock

COPY app ./app
COPY migrations ./migrations

RUN groupadd --system nutripilot && useradd --system --gid nutripilot nutripilot
USER nutripilot

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
