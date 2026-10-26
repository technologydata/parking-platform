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

## Database changes made by hand

`create_all` creates missing tables but never changes existing ones. If you ran the project before the reminder feature, run this once:

```sql
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS reminder_sent_at timestamptz;
```

A fresh clone gets the column automatically.

## Notes

- Never commit `.env`. It holds secrets.
- Postgres only reads its init scripts and password on the very first start. Use `docker compose down -v` to reset.
- If port 5432 is already used on your machine, change it to `"5433:5432"` in `e.yml`.