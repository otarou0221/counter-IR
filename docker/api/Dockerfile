FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY docker/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY alembic.ini ./alembic.ini
COPY src/cardboard_counter_v2/__init__.py ./src/cardboard_counter_v2/__init__.py
COPY src/cardboard_counter_v2/common ./src/cardboard_counter_v2/common
COPY src/cardboard_counter_v2/api ./src/cardboard_counter_v2/api
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["uvicorn", "cardboard_counter_v2.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
