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
4. Start everything. The API container builds the database tables itself (`alembic upgrade head`):
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
- `api/alembic/` - database migrations (one file per schema change)
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
3. Import **S1 first**, then the others: **Workflows -> (menu) -> Import from file**, and choose a file from `n8n/workflows/`. Order: `S1-send-notification.json`, then `W0`, `W1` and `W2`.
4. Open every **HTTP Request** node and re-select the `Parking Internal API` credential. Credential ids differ between machines, so the imported reference may show as missing.
5. Open the `Send via S1` node in W1 and W2, and re-select **S1 - Send Notification** as the workflow to call. Sub-workflow ids also differ between machines.
6. **Publish S1.** A published workflow can only call a sub-workflow that is also published. S1 has no schedule, so it only runs when called.
7. Publish W1 or W2 only when you want them to run on their 5-minute schedule.

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
| `GET /internal/bookings/due-reminders` | n8n | Bookings starting within the next 30 minutes that have not been reminded yet |
| `POST /internal/bookings/{id}/reminder-sent` | n8n | Records that a reminder was sent (`reminder_sent_at`) |

`/internal/` endpoints need the `X-API-Key` header.

## Database migrations (Alembic)

The schema is managed by Alembic. The migration files in `api/alembic/versions/` are the single source of truth. The API container runs `alembic upgrade head` every time it starts, so a fresh database builds itself and an existing one catches up.

### Making a schema change

1. Edit the table definitions in `api/app/models.py` and save.
2. Generate a migration. The number must follow the last file in `api/alembic/versions/`:
   ```powershell
   docker exec parking-api alembic revision --autogenerate -m "short description" --rev-id 0003
   ```
3. **Read the generated file.** Autogenerate is a draft. `upgrade()` should contain only the change you meant.
4. Apply it:
   ```powershell
   docker exec parking-api alembic upgrade head
   ```
5. Check that the models and the database agree. It should print "No new upgrade operations detected.":
   ```powershell
   docker exec parking-api alembic check
   ```
6. Commit `models.py` and the new migration file **together**.

Uvicorn's auto-reload does not run migrations. Only a container start or `alembic upgrade head` does.

### Useful commands

| Task | Command |
|---|---|
| Which revision is the database at? | `docker exec parking-api alembic current` |
| Migration history | `docker exec parking-api alembic history` |
| Undo the last migration (**deletes data in dropped columns, use on throwaway databases only**) | `docker exec parking-api alembic downgrade -1` |

Alembic connects to whatever `DATABASE_URL` says. To run it against another database for one command, override it:
`docker exec -e "DATABASE_URL=postgresql+psycopg://<user>:<password>@postgres:5432/<database>" parking-api alembic upgrade head`

### If you ran the project before Alembic was added

Your database has the tables but no `alembic_version` table. The API would try to create tables that already exist and keep restarting. Pick one:

- **No data you need (simplest):** `docker compose down -v`, then `docker compose up -d --build`. This deletes **all** data, including your n8n workflows and credentials.
- **Keep your data:** first make sure your database matches `0001` (the `bookings.reminder_sent_at` column exists and the `uq_active_slot_per_day` index covers `BOOKED` and `CHECKED_IN`). Then stamp it, and start the stack:
  ```powershell
  docker compose run --rm api alembic stamp 0001
  docker compose up -d --build
  ```

## Notes

- Never commit `.env`. It holds secrets.
- Postgres only reads its init scripts and password on the very first start. Use `docker compose down -v` to reset.
- If port 5432 is already used on your machine, change it to `"5433:5432"` in `e.yml`.