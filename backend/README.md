# v2 backend

Python API, worker, and agent loop for the expense-capture platform.
This package is independent of `v1/` and does not import Version 1 modules.

## Local run

```bash
cd v2/backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env
uvicorn app.api:app --reload
```

In another terminal:

```bash
cd v2/backend
source .venv/bin/activate
python -m app.worker
```

## Tests

```bash
cd v2/backend
source .venv/bin/activate
pytest
```

Docker Compose stays at `v2/` and builds this folder. See the [product README](../README.md).
