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
| Mailpit (caught emails) | http://localhost:8025 |

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
2. Create the two credentials the workflows use (**Credentials -> Create credential**):
   - **Header Auth**, named `Parking Internal API`
     - Header **Name**: `X-API-Key`
     - Header **Value**: the `INTERNAL_API_KEY` from your own `.env`
   - **SMTP**, named `Parking SMTP` (it points at the local Mailpit container)
     - **User** / **Password**: `parking` / `parking` (Mailpit accepts any login)
     - **Host**: `mailpit`, **Port**: `1025`, **SSL/TLS**: off
3. Import **S1 first**, then **E1**, then the others: **Workflows -> (menu) -> Import from file**, using the files in `n8n/workflows/`. Order: `S1-send-notification.json`, `E1-error-handler.json`, then `W0`, `W1` and `W2`.
4. Open the `Send email` node in S1 and re-select the `Parking SMTP` credential. Open every **HTTP Request** node and re-select `Parking Internal API`. Credential ids differ between machines, so the imported reference may show as missing.
5. Open the `Send via S1` node in E1, W1 and W2, and re-select **S1 - Send Notification** as the workflow to call. Sub-workflow ids also differ between machines.
6. Open the **Settings** of W1 and W2 and set **Error Workflow** to **E1 - Error Handler** again. The imported link points at an id from the original machine.
7. **Publish S1 and E1.** A published workflow can only call a sub-workflow that is also published, and E1 sends its alert through S1. Neither has a schedule, so they only run when called.
8. Publish W1 or W2 only when you want them to run on their 5-minute schedule.

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

## Notifications

All workflows send messages through the shared sub-workflow **S1 - Send Notification**. S1 takes `employee_id`, `message` and an optional `subject`, sends an email and returns:

| Field | Meaning |
|---|---|
| `channel` | `EMAIL` |
| `delivery_status` | `SENT` or `FAILED` |
| `error` | The error text when the send failed, otherwise empty |

**Mailpit** catches every email, so nothing leaves your machine. Open http://localhost:8025 to read them. Messages live in memory and disappear when the container restarts.

The recipient is a placeholder, `<employee_id>@parking.local`, because the API stores no email addresses yet. To use a real mail server later, change only the `Parking SMTP` credential and the address in S1's `Build email` node.

W2 marks a reminder as sent only when S1 returns `SENT`, so a failed send is retried on the next run.

## Error alerts

**E1 - Error Handler** emails `ADMIN@parking.local` (visible in Mailpit) whenever a linked workflow run ends in an error. W1 and W2 are linked to it in their **Settings -> Error Workflow**. S1 and E1 are not linked: S1 failures end the caller's run, which already alerts, and E1 pointing at itself could loop.

E1 only runs for **automatic** executions. Clicking **Execute workflow** never triggers it.

| Alert's failed node | Meaning | What to do |
|---|---|---|
| `Get overdue bookings` / `Get due reminders` | The API call failed (API down, wrong key) | Check `docker compose ps` and the API log |
| `Alert: notification failed` | An email was not delivered (`delivery_status` was not `SENT`) | Check Mailpit and the `Parking SMTP` credential |
| `Alert: release failed` (W1) | The release call failed with something other than the expected conflict | Read the error text in the alert, then the API log |
| `Alert: mark failed` (W2) | The reminder email went out but could not be marked as sent, so it may be sent again | Read the error text in the alert, then the API log |

**Expected conflicts stay quiet.** If an employee checks in just after the overdue or due list was made, the API answers 409. W1 and W2 recognise those messages and carry on without an alert.

**Known limits:** a lasting fault alerts on every run (every 5 minutes). If Mailpit itself is down, the alert cannot be delivered either, because E1 sends through S1.

## Notes

- Never commit `.env`. It holds secrets.
- Postgres only reads its init scripts and password on the very first start. Use `docker compose down -v` to reset.
- If port 5432 is already used on your machine, change it to `"5433:5432"` in `docker-compose.yml`.