FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install only runtime libraries; the worker/data adapter can use the same image.
COPY pyproject.toml README.md ./
COPY src/ ./src/
# Soccerdata's tls_requests dependency downloads a native .so into its package
# directory on first use. Provision it while building as root; the runtime
# user intentionally cannot write to /usr/local/lib/python3.11/site-packages.
RUN python -m pip install --no-cache-dir '.[web,model,data]' \
    && python -c 'from tls_requests.models.libraries import TLSLibrary; TLSLibrary.load()' \
    && groupadd --system --gid 10001 football \
    && useradd --system --uid 10001 --gid football --no-create-home football

USER football
# Fail the image build if the native library cannot be read by the runtime user.
RUN python -c 'from tls_requests.models.libraries import TLSLibrary; TLSLibrary.load()'
EXPOSE 8000

CMD ["uvicorn", "football_predictor.web.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
