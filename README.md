# Parking Platform (learning project)

A local setup for a parking-management system.
FastAPI owns the business logic, n8n orchestrates workflows, and Postgres and Redis store the data.

## Architecture

```
n8n (5678) --HTTP + X-API-Key--> FastAPI (8000) --> Postgres "parking"
   |                                  +-----------> Redis (booking locks)
   +--> Postgres "n8n" (n8n's own workflows and credentials)
```

Rule: n8n never writes to the parking database directly. It only calls the API.

## Prerequisites

- A Docker-compatible engine, for example Rancher Desktop with the **dockerd** engine
- Git
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- VS Code (optional)

## First-time setup

1. Clone the repository and open the folder.
2. Create your own `.env` from the example:
   ```powershell
   Copy-Item .env.example .env
   ```
3. Edit `.env` and replace the placeholder values. Generate random keys with:
   ```powershell
   [guid]::NewGuid().ToString("N")
   ```
4. Start everything:
   ```powershell
   docker compose up -d --build
   ```
5. Install the Python packages locally, so your editor can see them:
   ```powershell
   cd api
   uv sync
   ```

## URLs

| What | Address |
|---|---|
| API health check | http://localhost:8000/health |
| API docs (Swagger) | http://localhost:8000/docs |
| n8n editor | http://localhost:5678 |

On first visit, n8n asks you to create your own owner account.

## Daily commands

| Task | Command |
|---|---|
| Start | `docker compose up -d` |
| Stop (data kept) | `docker compose down` |
| View API logs | `docker compose logs -f api` |
| Reset all data (deletes everything) | `docker compose down -v` |

## Project layout

- `api/` - FastAPI service (managed with uv)
- `postgres/init/` - SQL that creates the n8n database on first start
- `n8n/workflows/` - exported n8n workflow JSON files
- `docker-compose.yml` - defines all services

## Notes

- Never commit `.env`. It holds secrets.
- Postgres only reads its init scripts and password on the very first start. Use `docker compose down -v` to reset.
- If port 5432 is already used on your machine, change it to `"5433:5432"` in `e.yml`.