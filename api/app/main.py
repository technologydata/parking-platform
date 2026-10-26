# ============================================================
# SECTION 1: IMPORTS (tools we borrow from other libraries)
# ============================================================

# os: lets us read environment variables (values set in docker-compose.yml)
import os

# asynccontextmanager: a decorator that turns our startup/shutdown function into
# something FastAPI can run in two phases (before and after the API serves requests)
from contextlib import asynccontextmanager

# date: a calendar date like 2026-10-15
# datetime: a date plus a time like 2026-10-15 09:00
# timedelta: a length of time, e.g. "15 minutes", used to subtract the grace period
# timezone: lets us say a time is in UTC
from datetime import date, datetime, timedelta, timezone

# Literal: restricts a value to a fixed list of choices (e.g. only "BIKE" or "CAR")
from typing import Literal

# redis: the Python client used to talk to the Redis container (we use it for locks)
import redis

# Depends: tells FastAPI "call this helper function first and give me its result"
# FastAPI: the web framework itself
# Header: reads a value from the HTTP request headers (we use it for X-API-Key)
# HTTPException: lets us return an error response such as 401 or 409
from fastapi import Depends, FastAPI, Header, HTTPException

# BaseModel: the parent class for request-body shapes; it validates incoming JSON
from pydantic import BaseModel

# func: SQL functions such as COUNT()
# select: builds a SELECT query
# text: lets us write a small piece of raw SQL (we use "SELECT 1")
from sqlalchemy import func, select, text

# IntegrityError: the error raised when the database rejects data
# (for example, the unique index blocking a double booking)
from sqlalchemy.exc import IntegrityError

# Session: the type of a database session (one "conversation" with Postgres)
from sqlalchemy.orm import Session

# From our own file database.py:
#   Base         = parent class of all tables
#   SessionLocal = factory that creates database sessions
#   engine       = the connection to Postgres
#   get_db       = helper that gives each request its own session
# The dot means "from the file next to this one".
from .database import Base, SessionLocal, engine, get_db

# From our own file models.py: the two table classes
from .models import ACTIVE_STATUSES, Booking, Slot


# ============================================================
# SECTION 2: SETTINGS READ FROM THE ENVIRONMENT
# ============================================================

# Connect to Redis. The address comes from the REDIS_URL environment variable
# (set in docker-compose.yml). decode_responses=True makes Redis return normal
# text instead of raw bytes.
r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

# The secret that n8n must send to call /internal endpoints.
# The real value lives in .env and reaches us through docker-compose.yml,
# so it is never written in the code. If the variable is missing, the API
# stops at startup with a KeyError, which is what we want.
INTERNAL_API_KEY = os.environ["INTERNAL_API_KEY"]


# ============================================================
# SECTION 3: STARTUP CODE (lifespan)
# ============================================================

# Turns the function below into a two-phase block: code before "yield" runs at
# startup, code after "yield" runs at shutdown.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create the slots and bookings tables if they don't exist yet.
    # It never changes or deletes tables that already exist.
    Base.metadata.create_all(engine)

    # Open a database session. "with" closes it automatically when the block ends.
    with SessionLocal() as db:
        # Count the rows in the slots table. We only add demo slots when it's empty,
        # so restarting the API never creates duplicates.
        if db.scalar(select(func.count(Slot.id))) == 0:
            # Add 10 bike slots: B-01, B-02, ... B-10
            # {i:02d} means "write the number with at least 2 digits" (1 becomes 01)
            for i in range(1, 11):
                db.add(Slot(zone="BIKE", code=f"B-{i:02d}"))
            # Add 5 car slots: C-01 ... C-05
            for i in range(1, 6):
                db.add(Slot(zone="CAR", code=f"C-{i:02d}"))
            # Save all the new slots to the database in one go
            db.commit()

    # Pause here. The API now starts serving requests.
    # Shutdown code (if we ever need it) would go after this line.
    yield


# Create the API application.
# title and version appear on the /docs page.
# lifespan=lifespan connects the startup code above to the app.
app = FastAPI(title="Parking API", version="0.1.0", lifespan=lifespan)


# ============================================================
# SECTION 4: REQUEST SHAPE AND HELPERS
# ============================================================

# Describes the JSON body that POST /bookings must receive.
# FastAPI checks every request against it and rejects bad input with a 422 error
# before our endpoint code runs.
class BookingIn(BaseModel):
    # Who is booking, e.g. "E1001". Must be text.
    employee_id: str
    # Which kind of parking. Only "BIKE" or "CAR" is accepted.
    zone: Literal["BIKE", "CAR"]
    # The day the parking is for, e.g. 2026-10-15. Must be a valid date.
    booking_date: date
    # The time the employee promised to arrive, e.g. 2026-10-15T09:00:00+05:30
    arrival_by: datetime


# Converts a Booking database row into a plain dictionary that can be sent as JSON.
# "b: Booking" says the input is a Booking; "-> dict" says it returns a dictionary.
def to_dict(b: Booking) -> dict:
    return {
        # Booking number
        "id": b.id,
        # Who booked
        "employee_id": b.employee_id,
        # Which slot they got (the id from the slots table)
        "slot_id": b.slot_id,
        # .isoformat() turns the date into text like "2026-10-15"
        "booking_date": b.booking_date.isoformat(),
        # Same for the date and time, e.g. "2026-10-15T03:30:00+00:00"
        "arrival_by": b.arrival_by.isoformat(),
        # Current status, e.g. "BOOKED"
        "status": b.status,
        # When the reminder was sent, or None if it hasn't been sent yet.
        # The "if" avoids calling .isoformat() on an empty value, which would raise an error.
        "reminder_sent_at": b.reminder_sent_at.isoformat() if b.reminder_sent_at else None,

    }


# A security check that FastAPI runs BEFORE the endpoints that use it.
# Header(...) means the request MUST include a header named X-API-Key.
# FastAPI turns the parameter name x_api_key into the header name X-API-Key.
def require_internal_key(x_api_key: str = Header(...)):
    # If the key sent doesn't match our secret...
    if x_api_key != INTERNAL_API_KEY:
        # ...stop here and return 401 (Unauthorized). The endpoint never runs.
        raise HTTPException(status_code=401, detail="Invalid API key")


# ============================================================
# SECTION 5: ENDPOINTS
# ============================================================

# ---------- GET /health : is everything alive? ----------

# Registers this function as the handler for GET requests to /health
@app.get("/health")
# db: Session = Depends(get_db) means "FastAPI, call get_db() and give me a
# database session as db". The session is closed after the request.
def health(db: Session = Depends(get_db)):
    # Run the simplest possible SQL query. If Postgres is down, this raises an error.
    db.execute(text("SELECT 1"))
    # Ask Redis to reply "PONG". If Redis is down, this raises an error.
    r.ping()
    # If we got here, both are reachable
    return {"status": "ok"}


# ---------- GET /slots/availability : how many slots are free? ----------

# Handles GET /slots/availability?zone=BIKE&day=2026-10-15
@app.get("/slots/availability")
# zone and day are read from the URL. Literal accepts only BIKE or CAR, and
# date accepts only a valid date. Anything else gets an automatic error.
def availability(zone: Literal["BIKE", "CAR"], day: date, db: Session = Depends(get_db)):
    # Total number of slots that exist in this zone.
    # SQL: SELECT COUNT(id) FROM slots WHERE zone = :zone
    total = db.scalar(select(func.count(Slot.id)).where(Slot.zone == zone))

    # Number of slots already booked on this day.
    # The bookings table has no zone column, so we join to slots to filter by zone.
    booked = db.scalar(
        select(func.count(Booking.id))
        # Link each booking to its slot row
        .join(Slot, Slot.id == Booking.slot_id)
        # Same zone, same date, and still active (cancelled bookings don't count)
        .where(Slot.zone == zone, Booking.booking_date == day, Booking.status.in_(ACTIVE_STATUSES))
    )

    # Send the numbers back as JSON
    return {
        "zone": zone,
        # Turn the date into text like "2026-10-15"
        "date": day.isoformat(),
        "total": total,
        "booked": booked,
        # Free slots = all slots minus booked ones
        "available": total - booked,
    }


# ---------- POST /bookings : create a booking ----------

# Handles POST /bookings. status_code=201 means "Created", the standard
# success code for a new record.
@app.post("/bookings", status_code=201)
# body: BookingIn = the JSON the client sent, already validated against BookingIn
def create_booking(body: BookingIn, db: Session = Depends(get_db)):
    # STEP 1: Ask Redis for a lock named after the zone and date,
    # e.g. "lock:slots:BIKE:2026-10-15". Only one request at a time can hold it,
    # so two people can't pick the same slot at the same moment.
    #   timeout=5          the lock expires by itself after 5 seconds, so a crash
    #                      can't block bookings forever
    #   blocking_timeout=3 wait at most 3 seconds to get the lock
    lock = r.lock(f"lock:slots:{body.zone}:{body.booking_date}", timeout=5, blocking_timeout=3)

    # If we couldn't get the lock within 3 seconds, tell the caller to retry.
    # 503 means "service temporarily unavailable".
    if not lock.acquire():
        raise HTTPException(status_code=503, detail="Busy, please retry")

    # "try ... finally" guarantees the lock is released, even if an error happens
    try:
        # STEP 2: Does this employee already have an active booking for this date?
        # SQL: SELECT id FROM bookings WHERE employee_id = ... AND booking_date = ... AND status = 'BOOKED'
        existing = db.scalar(
            select(Booking.id).where(
                Booking.employee_id == body.employee_id,
                Booking.booking_date == body.booking_date,
                Booking.status.in_(ACTIVE_STATUSES),
            )
        )
        # If a booking was found, refuse with 409 (Conflict)
        if existing:
            raise HTTPException(status_code=409, detail="Employee already has a booking for this date")

        # STEP 3: Find a free slot.
        # "taken" is a subquery: the slot ids already booked on this date.
        taken = select(Booking.slot_id).where(
            Booking.booking_date == body.booking_date, Booking.status.in_(ACTIVE_STATUSES)
        )
        # Pick the first slot in the requested zone whose id is NOT in "taken".
        #   order_by(Slot.id) -> lowest slot number first
        #   limit(1)          -> only one row
        #   .first()          -> the slot itself, or None if there isn't one
        slot = db.scalars(
            select(Slot).where(Slot.zone == body.zone, Slot.id.not_in(taken)).order_by(Slot.id).limit(1)
        ).first()
        # No free slot found -> refuse with 409
        if not slot:
            raise HTTPException(status_code=409, detail="No slots available")

        # STEP 4: Build the new booking row in memory
        booking = Booking(
            employee_id=body.employee_id,
            slot_id=slot.id,
            booking_date=body.booking_date,
            arrival_by=body.arrival_by,
        )
        # Stage it for saving (nothing is written to the database yet)
        db.add(booking)

        # Try to save it
        try:
            db.commit()
        # If the unique index from models.py rejects it, another request took this
        # slot in the same instant. This is the backup guard behind the Redis lock.
        except IntegrityError:
            # Undo the failed save so the session is usable again
            db.rollback()
            raise HTTPException(status_code=409, detail="Slot just taken, retry")

        # Reload the row from the database so id and default values are filled in
        db.refresh(booking)
        # Send the saved booking back as JSON
        return to_dict(booking)

    # This block ALWAYS runs at the end, whether the code above returned or raised an error
    finally:
        try:
            # Release the Redis lock so the next request can proceed
            lock.release()
        except Exception:
            # The lock may have already expired by itself, which is fine
            pass


# ---------- GET /internal/bookings/overdue : used by n8n ----------

# dependencies=[Depends(require_internal_key)] runs the API key check first.
# If the key is wrong, the function body below never runs.
@app.get("/internal/bookings/overdue", dependencies=[Depends(require_internal_key)])
# grace_minutes comes from the URL, e.g. ?grace_minutes=60. It defaults to 30.
def overdue_bookings(grace_minutes: int = 30, db: Session = Depends(get_db)):
    # The cutoff moment = now (in UTC) minus the grace period.
    # Example: now is 10:00 and grace is 30 min, so cutoff is 9:30.
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=grace_minutes)

    # Find bookings that are still BOOKED and whose promised arrival time is
    # BEFORE the cutoff (their grace period has run out).
    # SQL: SELECT * FROM bookings WHERE status = 'BOOKED' AND arrival_by < :cutoff
    # .all() returns every match as a list.
    rows = db.scalars(
        select(Booking).where(Booking.status == "BOOKED", Booking.arrival_by < cutoff)
    ).all()

    # Return an object (not a bare list):
    #   count    = how many overdue bookings were found (len(rows))
    #   bookings = the bookings themselves, converted with to_dict
    # n8n stops a flow when a node returns an empty list, but an object always
    # gives it something to inspect, even when the count is 0.
    return {"count": len(rows), "bookings": [to_dict(b) for b in rows]}

def get_booking_or_404(db: Session, booking_id: int) -> Booking:
    # Look up one booking by its id (SQL: SELECT * FROM bookings WHERE id = :booking_id)
    booking = db.get(Booking, booking_id)
    # No such booking -> return 404 (Not Found)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


# ---------- POST /bookings/{booking_id}/check-in : employee arrived ----------

# {booking_id} in the URL is a variable part, e.g. POST /bookings/2/check-in
@app.post("/bookings/{booking_id}/check-in")
def check_in(booking_id: int, db: Session = Depends(get_db)):
    # Find the booking, or return 404 if the id doesn't exist
    booking = get_booking_or_404(db, booking_id)

    # Only an active booking can be checked in.
    # A booking that is already CHECKED_IN, NO_SHOW or CANCELLED is refused with 409 (Conflict).
    if booking.status != "BOOKED":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot check in a booking with status {booking.status}",
        )

    # Mark the employee as arrived. W1 only looks at BOOKED rows, so it will now skip this one.
    booking.status = "CHECKED_IN"
    db.commit()  # save the change to Postgres
    db.refresh(booking)  # reload the row so we return what is really stored
    return to_dict(booking)

# ---------- POST /internal/bookings/{booking_id}/release : used by n8n (W1) ----------

# dependencies=[...] runs the API key check first, the same as the overdue endpoint
@app.post(
    "/internal/bookings/{booking_id}/release",
    dependencies=[Depends(require_internal_key)],
)
def release_booking(booking_id: int, db: Session = Depends(get_db)):
    # Find the booking, or return 404 if the id doesn't exist
    booking = get_booking_or_404(db, booking_id)

    # Only a booking that is still BOOKED can be released.
    # If the employee checked in (or it was already released), refuse with 409.
    # This protects people who arrived between n8n's query and its release call.
    if booking.status != "BOOKED":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot release a booking with status {booking.status}",
        )

    # Mark as a no-show. The unique index in models.py only counts BOOKED rows,
    # so this also frees the slot for someone else on that date.
    booking.status = "NO_SHOW"
    db.commit()  # save the change to Postgres
    db.refresh(booking)  # reload the row so we return what is really stored
    return to_dict(booking)


# ---------- GET /internal/bookings/due-reminders : used by n8n (W2) ----------

@app.get("/internal/bookings/due-reminders", dependencies=[Depends(require_internal_key)])
def due_reminders(minutes_before: int = 30, db: Session = Depends(get_db)):
    # The reminder window is from "now" to "now + minutes_before" (30 by default, from the SRS)
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=minutes_before)

    # SQL equivalent:
    # SELECT * FROM bookings
    # WHERE status = 'BOOKED' AND reminder_sent_at IS NULL
    #   AND arrival_by > :now AND arrival_by <= :window_end
    # ORDER BY arrival_by
    rows = db.scalars(
        select(Booking)
        .where(
            Booking.status == "BOOKED",           # still an active, not-yet-arrived booking
            Booking.reminder_sent_at.is_(None),   # "IS NULL": no reminder sent yet
            Booking.arrival_by > now,             # arrival time hasn't passed
            Booking.arrival_by <= window_end,     # and is within the next 30 minutes
        )
        .order_by(Booking.arrival_by)             # soonest arrival first
    ).all()

    # Same shape as the overdue endpoint: an object with a count, never a bare list
    return {"count": len(rows), "bookings": [to_dict(b) for b in rows]}


# ---------- POST /internal/bookings/{booking_id}/reminder-sent : used by n8n (W2) ----------

@app.post(
    "/internal/bookings/{booking_id}/reminder-sent",
    dependencies=[Depends(require_internal_key)],
)
def mark_reminder_sent(booking_id: int, db: Session = Depends(get_db)):
    # Find the booking, or return 404 if the id doesn't exist
    booking = get_booking_or_404(db, booking_id)

    # Only a still-active booking can have its reminder marked
    if booking.status != "BOOKED":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot mark a reminder for a booking with status {booking.status}",
        )

    # Refuse a second mark, so a duplicate call is visible instead of silently overwriting the time
    if booking.reminder_sent_at is not None:
        raise HTTPException(status_code=409, detail="Reminder already marked as sent")

    # Record when the reminder went out. The due-reminders query skips this booking from now on.
    booking.reminder_sent_at = datetime.now(timezone.utc)
    db.commit()           # save the change to Postgres
    db.refresh(booking)   # reload the row so we return what is really stored
    return to_dict(booking)