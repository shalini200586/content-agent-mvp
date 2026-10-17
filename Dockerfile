# API server: FastAPI on port 8000, with the drafting pipeline behind it.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONTENT_AGENT_DB=/data/content_agent.db

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[web]"

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "content_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
