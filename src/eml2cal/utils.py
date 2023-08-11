import subprocess
from datetime import timedelta
from typing import Optional, Any


def chained_get(d: dict[str, Any], key: str, default: Any = None) -> Any:
    """Convenience function to access attributes of nested dicts.

    :param d: The dict to search.
    :param key: A string containing the chain of attribute names to search for, separately by `.`.
    :param default: A value to return if nothing is found at the requested location.
    """
    keys = key.split(".")
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


def get_pass(pass_name: str, pass_exec: str = "/usr/bin/oass") -> str:
    """Get a password using the `pass` command line utility.

    :param pass_name: The name of the password as stored in `pass`.
    :param pass_exec: The path to the `pass` executable to use.
    :return: The password as a string.
    """
    output = subprocess.run([pass_exec, "show", pass_name], capture_output=True)
    if output.returncode:
        raise SystemError(output.stderr)
    else:
        return output.stdout.decode()
