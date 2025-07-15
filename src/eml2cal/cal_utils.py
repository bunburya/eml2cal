import logging
import shlex
import subprocess
import time
from datetime import timedelta, datetime, date
from typing import Optional, Any

import caldav
import icalendar

from eml2cal.summary import Summary, EventSummary
from eml2cal.utils import chained_get

logger = logging.getLogger(__name__)


def get_calendar(client: caldav.DAVClient, cal_url: str) -> Optional[caldav.Calendar]:
    return client.calendar(cal_url)


def get_conflicts(cal: caldav.Calendar, event: icalendar.Event):
    """Check if the given CalDAV calendar contains any events which conflict with the given iCalendar event.

    :return: A list of conflicting :class:`icalendar.Event` objects, as retrieved from the CalDAV server.
    """
    start: Optional[date] = getattr(event.get("dtstart"), "dt", None)
    if start is None:
        raise ValueError("Event must have start date.")
    end: Optional[date] = getattr(event.get("dtend"), "dt", None)
    logger.debug(f"END: {end}")

    # Convert dates to datetimes: `start` becomes the start of the day, `end` becomes the start of the next day.
    # This is a bit hacky and probably vulnerable to corner cases but is basically intended to ensure we can properly
    # search for conflicting events in the calendar.
    if not isinstance(start, datetime):
        start = datetime(start.year, start.month, start.day, 0, 0)
        if end is None:
            end = start + timedelta(days=1)
    if (end is not None) and (not isinstance(end, datetime)):
        end = datetime(end.year, end.month, end.day, 0, 0) + timedelta(days=1)

    if end is None:
        # Strangely, where we are searching for an event that has no end time, `start` seems to stop being inclusive,
        # ie, we can only find the event by searching from (start - 1 second) to (start + 1 second).
        end = start + timedelta(seconds=1)
        start -= timedelta(seconds=1)
    conflicting = cal.search(
        start=start,
        end=end,
        event=True
    )
    return [e.icalendar_component for e in conflicting]


def add_events_to_cal(cal: caldav.Calendar, events: list[icalendar.Event], summary: Summary) -> list[icalendar.Event]:
    cal_name = cal.name
    added = []
    for e in events:
        event_name = e.get("summary", "[no summary]")
        conflicts = get_conflicts(cal, e)
        if not conflicts:
            ical_str = e.to_ical().decode()
            cal.save_event(ical_str)
            logger.debug(f"Added event {event_name} to calendar {cal_name}.")
            added.append(e)
        else:
            logger.error(f"Event {event_name} conflicts with {len(conflicts)} events in calendar {cal_name}. "
                         "Did not add.")
            summary.conflicts.append(EventSummary.from_event(e, len(conflicts)))
        time.sleep(1)
    return added


def save_events(events: list[icalendar.Event], config: dict[str, Any], summary: Summary) -> list[icalendar.Event]:
    """Access a calendar over CalDAV and add the given events.

    :param events: :class:`icalendar.Event` objects to add.
    :param config: A dict representing the user configuration.
    :param summary: A summary of the process, which will be updated in-place with duplicate events.
    """
    url = chained_get(config, "calendar.caldav.calendar_url")
    uname = chained_get(config, "calendar.caldav.username")
    passwd_cmd = chained_get(config, "calendar.caldav.password_cmd")
    if not (url and uname and passwd_cmd):
        raise ValueError("Could not find CalDAV login details in configuration.")
    output = subprocess.run(shlex.split(passwd_cmd), capture_output=True)
    if output.returncode:
        raise SystemError(output.stderr)
    passwd = output.stdout.decode().strip()
    with caldav.DAVClient(url=url, username=uname, password=passwd) as client:
        cal = client.calendar(url=url)
        added = add_events_to_cal(cal, events, summary)
    logger.info(f"Saved {len(added)} events to calendar at `{url}`. "
                f"{len(summary.conflicts)} not saved due to conflicting events.")
    return added
