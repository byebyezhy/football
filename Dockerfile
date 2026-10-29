FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install only runtime libraries; the worker/data adapter can use the same image.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir '.[web,model,data]' \
    && groupadd --system --gid 10001 football \
    && useradd --system --uid 10001 --gid football --no-create-home football

USER football
EXPOSE 8000

CMD ["uvicorn", "football_predictor.web.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
