import logging

import caldav
import icalendar


def get_conflicts(cal: caldav.Calendar, event: icalendar.Event):
    """Check if the given CalDAV calendar contains any events which conflict with the given iCalendar event.

    :return: A list of conflicting :class:`icalendar.Event` objects, as retrived from the CalDAV server.
    """
    conflicting = cal.search(
        start=event.get("dtstart"),
        end=event.get("dtend"),
        event=True
    )
    return [e.icalendar_component for e in conflicting]


def add_events(cal: caldav.Calendar,
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
