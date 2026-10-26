from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

# Statuses that occupy a parking slot. BOOKED = reserved, CHECKED_IN = vehicle has arrived.
# NO_SHOW and CANCELLED are not here, so those bookings free the slot.
ACTIVE_STATUSES = ("BOOKED", "CHECKED_IN")

class Slot(Base):
    __tablename__ = "slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone: Mapped[str] = mapped_column(String(10), index=True)  # BIKE / CAR
    code: Mapped[str] = mapped_column(String(20), unique=True)


class Booking(Base):
    __tablename__ = "bookings"
    # Safety net: a slot can have only ONE active booking per day
    __table_args__ = (
        Index(
            "uq_active_slot_per_day",
            "slot_id",
            "booking_date",
            unique=True,
            # Keep this list in sync with ACTIVE_STATUSES above.
            postgresql_where=text("status IN ('BOOKED', 'CHECKED_IN')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(30), index=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"))
    booking_date: Mapped[date] = mapped_column(Date)
    arrival_by: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(15), default="BOOKED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)