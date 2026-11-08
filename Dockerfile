ARG BASE_IMAGE=langchain-langgraph-rag:light
FROM ${BASE_IMAGE} AS dependencies

USER root
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt /tmp/custom-service-requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/custom-service-requirements.txt \
    && python -m pip check

# Both stages use existing local images. Copy only the resulting Python packages,
# leaving overwritten package layers and build-only files out of the runtime.
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
RUN useradd --uid 10001 --create-home learner \
    && mkdir -p /app/logs \
    && chown learner:learner /app/logs
WORKDIR /app

COPY --chown=learner:learner app ./app
COPY --chown=learner:learner migrations ./migrations
COPY --chown=learner:learner alembic.ini ./alembic.ini
USER learner

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).close()"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
