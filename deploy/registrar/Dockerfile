# Registrar API + publisher (SPEC §4.2). Build context: repository root.
FROM python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY deploy/registrar/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps .
COPY config ./config
ENV DATA_DIR=/data CONFIG_DIR=/app/config
EXPOSE 8080
# uvicorn's text access log is off: the app writes JSON access lines with the request id.
# Exactly ONE worker: each worker would start its own publisher and they would race.
CMD ["uvicorn", "--factory", "plot.api.main:create", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
