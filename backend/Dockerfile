FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/expense-agent

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN addgroup --system expense-agent \
    && adduser --system --ingroup expense-agent \
        --home /home/expense-agent expense-agent \
    && mkdir -p /app/data /home/expense-agent/.paddlex \
    && chown -R expense-agent:expense-agent /app /home/expense-agent

COPY --chown=expense-agent:expense-agent pyproject.toml README.md ./
COPY --chown=expense-agent:expense-agent app ./app

RUN pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.14.0 \
        torchvision==0.29.0 \
    && pip install ".[ocr]"

USER expense-agent

EXPOSE 8000

CMD ["uvicorn", "app.api:app", "--host=0.0.0.0", "--port=8000"]
