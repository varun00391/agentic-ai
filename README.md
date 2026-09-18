# Expense Capture Platform (v2)

Production-oriented multi-tenant expense capture. This tree is independent of
`v1/` and does not import Version 1 modules.

Layout:

```text
v2/
├── docker-compose.yml
├── .env / .env.example     # shared by frontend, API, worker, Postgres
├── README.md
├── backend/                # FastAPI, worker, agent
│   ├── Dockerfile
│   └── app/
└── frontend/               # React + Tailwind
    ├── Dockerfile
    └── src/
```

## Run with Docker

From `v2/`:

```bash
cd v2
cp .env.example .env
docker compose up --build
```

Open:

- App: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

Bootstrap login from `.env`:

- Email: `owner@example.com`
- Password: `change-me-now`

Nginx in the frontend container proxies `/api` to the API, so the browser stays on one origin.

## Run locally without Docker UI

Terminal 1, API:

```bash
cd v2/backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.api:app --reload
```

Terminal 2, worker:

```bash
cd v2/backend
source .venv/bin/activate
python -m app.worker
```

Terminal 3, frontend:

```bash
cd v2/frontend
npm install
npm run dev
```

Vite serves the app at http://localhost:5173 and proxies `/api` to http://localhost:8000.

## Tests

```bash
cd v2/backend
pip install -e ".[dev]"
pytest
```
