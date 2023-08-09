from datetime import timedelta
from typing import Optional, Any


def chained_get(d: dict[str, Any], *keys, default: Any = None) -> Any:
    """Convenience function to access attributes of nested dicts."""
    result = d.get(keys[0], {})
    for k in keys[1:]:
        if k in result:
            result = result[k]
        else:
            return default
    return result


def parse_duration(duration: str) -> timedelta:
    """Parse a duration string in the form HH:MM:SS into a timedelta."""
    h, m, s = duration.strip().split(":")
    return timedelta(
        hours=int(h),
        minutes=int(m),
        seconds=int(s)
    )


def airport_repr(name: Optional[str], iata: Optional[str]) -> Optional[str]:
    """Generate a textual representation of an airport name based on the information we have."""
    if name and (not iata):
        return name
    if iata and (not name):
        return iata
    if name and iata:
        return f"{name} ({iata})"
    else:
        return None

