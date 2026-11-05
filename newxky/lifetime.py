"""Offline startup cutoff, evaluated using the computer's clock in UTC+08:00."""
from datetime import datetime, timedelta, timezone


BEIJING = timezone(timedelta(hours=8))
EXPIRES_AT = datetime(2027, 7, 1, tzinfo=BEIJING)


def startup_allowed(now: datetime | None = None) -> bool:
    moment = datetime.now(timezone.utc) if now is None else now
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("An aware datetime is required")
    return moment < EXPIRES_AT
