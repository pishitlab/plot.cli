# Registrar API + publisher (SPEC §4.2). Build context: repository root.
FROM python:3.12.14-slim-trixie
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
CMD ["uvicorn", "--factory", "plot.api.main:create", "--host", "0.0.0.0", "--port", "8080"]
