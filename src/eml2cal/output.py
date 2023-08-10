import logging
import shlex
import subprocess
from datetime import timedelta
from typing import Optional, Any

import caldav
import icalendar

from eml2cal.utils import chained_get


def get_calendar(client: caldav.DAVClient, cal_url: str) -> Optional[caldav.Calendar]:
    return client.calendar(cal_url)


def get_conflicts(cal: caldav.Calendar, event: icalendar.Event):
    """Check if the given CalDAV calendar contains any events which conflict with the given iCalendar event.

    :return: A list of conflicting :class:`icalendar.Event` objects, as retrieved from the CalDAV server.
    """
    # TODO: Need to handle events that only specify a date.
    # This is a bit trickier as two all-day events aren't necessarily in conflict as such. Maybe we also check summaries
    # for equality - this may lead to some false negatives though (hopefully rare).
    logging.debug(f"EVENT NAME: {event.get('summary')}")
    start = getattr(event.get("dtstart"), "dt", None)
    logging.debug(f"START: {start}")
    if start is None:
        raise ValueError("Event must have start date.")
    end = getattr(event.get("dtend"), "dt", None)
    logging.debug(f"END: {end}")
    if end is None:
        # Strangely, where we are searching for an event that has no end time, `start` seems to stop being inclusive,
        # ie, we can only find the event by searching from (start - 1 second) to (start + 1 second).
        end = start + timedelta(seconds=1)
        start -= timedelta(seconds=1)
        logging.debug(f"ADJ. START: {start}")
        logging.debug(f"ADJ. END: {end}")
    conflicting = cal.search(
        start=start,
        end=end,
        event=True
    )
    logging.debug(f"FOUND: {len(conflicting)}")
    return [e.icalendar_component for e in conflicting]


def add_events_to_cal(cal: caldav.Calendar,
                      events: list[icalendar.Event]) -> list[tuple[icalendar.Event, list[icalendar.Event]]]:
    cal_name = cal.name
    all_conflicts = []
    for e in events:
        summary = e.get("summary", "[no summary]")
        conflicts = get_conflicts(cal, e)
        if not conflicts:
            cal.save_event(e.to_ical().decode())
            logging.debug(f"Added event {summary} to calendar {cal_name}.")
        else:
            logging.error(f"Event {summary} conflicts with {len(conflicts)} events in calendar {cal_name}. "
                          "Did not add.")
            all_conflicts.append((e, conflicts))
    return all_conflicts


def save_events(events: list[icalendar.Event],
                config: dict[str, Any]) -> list[tuple[icalendar.Event, list[icalendar.Event]]]:
    """Access a calendar over CalDAV and add the given events.

    :param events: :class:`icalendar.Event` objects to add.
    :param config: A dict representing the user configuration.
    """
    caldav_conf = chained_get(config, "output", "caldav")
    if not caldav_conf:
        raise ValueError("No `output.caldav` section found in configuration.")
    url = caldav_conf.get("calendar_url")
    uname = caldav_conf.get("username")
    passwd_cmd = caldav_conf.get("password_cmd")
    if not (url and uname and passwd_cmd):
        raise ValueError("Must specify `calendar_url`, `username` and `password_cmd` in configuration file.")
    output = subprocess.run(shlex.split(passwd_cmd), capture_output=True)
    if output.returncode:
        raise SystemError(output.stderr)
    passwd = output.stdout.decode().strip()
    with caldav.DAVClient(url=url, username=uname, password=passwd) as client:
        cal = client.calendar(url=url)
        dupes = add_events_to_cal(cal, events)
    logging.info(f"Saved {len(events)} events to calendar at `{url}`. {len(dupes)} not saved due to conflicting "
                 f"events.")
    return dupes
