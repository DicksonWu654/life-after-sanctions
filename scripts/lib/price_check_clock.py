"""Adapt the native price coverage check to a published generation date."""
import datetime as dt


def pin(namespace, as_of_utc):
    reference = dt.datetime.fromisoformat(as_of_utc.replace('Z', '+00:00'))
    if reference.tzinfo is None:
        raise ValueError('Price check reference must include a timezone')
    day = reference.astimezone(dt.timezone.utc).date()
    namespace['TODAY'] = day
    namespace['DAILY_TARGET'] = day-dt.timedelta(days=1)
