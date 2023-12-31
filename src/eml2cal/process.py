import logging
from datetime import datetime
from email.message import EmailMessage
from mailbox import Mailbox
from typing import Any, Optional

from icalendar import Event

from eml2cal.extractor import build_cmd, extract
from eml2cal.postprocess import reservation_to_ical_event, event_is_valid
from eml2cal.preprocess import preprocess_email
from eml2cal.schema_org import is_reservation
from eml2cal.summary import Summary, EmailSummary, EventEmailSummary

logger = logging.getLogger(__name__)


def process_email(email: EmailMessage, config: dict[str, Any]) -> list[Event]:
    """Process a single email, determining whether it contains one or more relevant events and returning a list of
    :class:`Event` objects if so.
    """
    logger.debug(f"Processing email: {email['Subject']}")
    cmd = build_cmd(config)
    thing_dicts = extract(cmd, email.as_bytes())
    reservation_dicts = list(filter(is_reservation, thing_dicts))
    if reservation_dicts:
        logger.debug(f"Found {len(reservation_dicts)} reservation objects.")

    events = []
    non_events = 0
    for d in reservation_dicts:
        try:
            e = reservation_to_ical_event(d, config)
            if e is not None:
                events.append(e)
            else:
                non_events += 1
        except Exception as e:
            logger.error(e)
            raise e

    valid_events = []
    if events:
        logger.debug(f"Generated {len(events)} calendar events.")
        for e in events:
            if event_is_valid(e):
                valid_events.append(e)
            else:
                non_events += 1
    if non_events:
        logger.debug(f"{non_events} reservations could not be converted to events.")
    return valid_events


def process_mailbox(mb: Mailbox, config: dict[str, Any], summary: Summary) -> Optional[list[Event]]:
    """Process each email in the given mailbox.

    :param mb: The :class:`Mailbox` to iterate for messages to process.
    :param config: A dict containing configuration options (parsed from a config file).
    :param summary: A summary that will be updated in-place with details obtained during processing.
    :return: A tuple containing:
        0. a list of :class:`Event` objects for events found in the mailbox.
        1. details of the events that were found.
    """
    events: list[Event] = []
    added_times: set[tuple[datetime, datetime]] = set()
    for msg in mb:
        summary.checked.append(EmailSummary.from_email(msg))
        try:
            preprocess_email(msg, config)
            new_events = process_email(msg, config)
            uniques = 0
            dupes = 0
            for e in new_events:
                t = (e.get("dtstart"), e.get("dtend"))
                if t not in added_times:
                    events.append(e)
                    added_times.add(t)
                    uniques += 1
                else:
                    dupes += 1
            if dupes + uniques != len(new_events):
                logging.warning(f"Number of duplicates ({dupes}) + number of uniques ({uniques}) does not equal number "
                                f"of found events ({len(new_events)}.")
            if new_events:
                summary.extracted.append(EventEmailSummary.from_email_and_stats(msg, len(new_events), uniques))
        except Exception as e:
            logger.error(f"Encountered error when processing email: {e}")
            summary.errors.append(msg)
            continue
    summary.end_time = datetime.now()

    return events
