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


## Importing the n8n workflows

Workflows are stored as JSON files in `n8n/workflows/`. Git cannot see workflows that only exist inside n8n, so every change is exported to this folder.

1. Open http://localhost:5678 and create your owner account (first visit only).
2. Create the credential the workflows use:
   - **Credentials -> Create credential -> Header Auth**
   - Name the credential `Parking Internal API`
   - Header **Name**: `X-API-Key`
   - Header **Value**: the `INTERNAL_API_KEY` from your own `.env`
3. Import each file: **Workflows -> (menu) -> Import from file**, choose a file from `n8n/workflows/`.
4. Open every **HTTP Request** node and re-select `Parking Internal API`. Credential ids differ between machines, so the imported reference may show as missing.
5. Workflows are exported as **inactive**. Switch one on only when you want it to run on its schedule.

### Exporting your own changes

Open the workflow, use the menu (three dots) -> **Download**, move the file into `n8n/workflows/`, and check it holds no secrets before committing.

## API endpoints

| Endpoint | Who calls it | Purpose |
|---|---|---|
| `GET /health` | anyone | Checks Postgres and Redis |
| `GET /slots/availability` | employees | Free slots for a zone and day |
| `POST /bookings` | employees | Create a booking |
| `POST /bookings/{id}/check-in` | gate (stand-in for now) | Marks the booking `CHECKED_IN` |
| `GET /internal/bookings/overdue` | n8n | Bookings still `BOOKED` after the grace period (default 30 min) |
| `POST /internal/bookings/{id}/release` | n8n | Sets a booking to `NO_SHOW`, which frees the slot |

`/internal/` endpoints need the `X-API-Key` header.


## Notes

- Never commit `.env`. It holds secrets.
- Postgres only reads its init scripts and password on the very first start. Use `docker compose down -v` to reset.
- If port 5432 is already used on your machine, change it to `"5433:5432"` in `e.yml`.