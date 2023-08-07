import json
import logging
import shlex
import subprocess
import sys
from argparse import ArgumentParser
from datetime import datetime, timedelta
from email.message import Message
from mailbox import Mailbox
from typing import Union, Any, IO, Optional, Callable

import platformdirs
from icalendar import Event, Alarm, vCalAddress, vText, Calendar
from pytz import utc

try:
    import tomllib as toml
except ImportError:
    import tomli as toml


def build_cmd(config: dict[str, Any]) -> list[str]:
    """Generate the command to run to invoke `kitinerary-extractor`."""
    cmd = shlex.split(config["command"])
    if "additional_extractors" in config:
        cmd.extend(["--additional-search-path", config["additional_extractors"]])
    return cmd


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


def apply_config(event: Event, config: dict[str, Any], reservation_type: str):
    """Apply options specified in the given config (eg, alarms, default duration, etc) to the given event, modifying
    it in place.

    :param event: :class:`Event` to modify.
    :param config: A dict containing configuration options, parsed from an appropriate TOML file.
    :param reservation_type: The type of reservation that `event` is referring to (per the schema.org ontology).
    """

    # Apply global config options first

    for a in config.get("attendees", []):
        add_attendee(event, a)

    # Then config options that are specific to reservation type

    specific_config = config.get(reservation_type)
    if not specific_config:
        return

    # Add default duration
    if (not (event.get("dtend") or event.get("duration"))) and (dur := specific_config.get("default_duration")):
        event.add("duration", parse_duration(dur))

    # Append categories
    if cats := specific_config.get("categories"):
        if existing := event.pop("categories"):
            existing_set = set(existing.cats)
            for c in cats:
                if c not in existing_set:
                    existing.cats.append()
            event.add("categories", existing.cats)

    # Add alarms
    if alarms := specific_config.get("alarms"):
        for dur in alarms:
            a = Alarm()
            a.add("action", "audio")
            a.add("trigger", parse_duration(dur))
            event.add_component(a)


def extract(cmd: list[str], input: bytes) -> list[dict[str, Any]]:
    """Run the kitinerary-extractor program specified by `cmd` on `input` and return the resulting JSON parsed into a
    list of dicts (each dict corresponding to an event).

    :param cmd: The command to run to invoke kitinerary-extractor (as a list of strings).
    :param input: Bytes to provide to kitinerary-extractor as input.
    :return: A list of dicts obtained by parsing the JSON output by kitinerary-extractor, each of which should conform
    to a schema.org schema. If no information can be extracted from the given file, an empty list will be returned.
    """
    output = subprocess.run(cmd, input=input, capture_output=True)
    if output.returncode:
        raise SystemError(output.stderr.decode())
    return json.loads(output.stdout)


def generic_parser(reservation_data: dict[str, Any]) -> Event:
    """Extract key details from a dict representing any type of Reservation. This function will generally be called by
    a Reservation-specific parser function to generate an :class:`Event` to use as a starting point. It should only be
    called directly where no Reservation-specific parser is available.

    :param reservation_data: A dict corresponding to a schema.org Reservation (as constructed from the JSON-LD produced
        by KItinerary).
    :return: An :class:`Event` object containing the key details.
    """
    res_for = reservation_data["reservationFor"]
    event = Event()
    # Assume that reservationFor is of type Event (technically it could be any Thing, but I believe KItinerary will
    # always produce an Event)
    if "name" in res_for:
        event.add("summary", res_for["name"])
    if "startDate" in res_for:
        event.add("dtstart", datetime.fromisoformat(res_for["startDate"]))
    if "endDate" in res_for:
        event.add("dtend", datetime.fromisoformat(res_for["endDate"]))
    return event


def flight_reservation_parser(reservation_data: dict[str, Any]) -> Event:
    """Extract details from a dict representing a FlightReservation.

    :param reservation_data: A dict corresponding to a schema.org FlightReservation (as constructed from the JSON-LD
        produced by KItinerary).
    :return: An :class:`Event` object containing the key details.
    """
    event = generic_parser(reservation_data)
    res_for = reservation_data["reservationFor"]

    airline_iata = res_for.get("airline", {}).get("iataCode", "")
    flight_iata = airline_iata + res_for.get("flightNumber")

    dep_airport = res_for.get("departureAirport")
    if dep_airport:
        dep_airport_name = dep_airport.get("name")
        dep_airport_iata = dep_airport.get("iataCode")
        dep_terminal = res_for.get("departureTerminal")
        if "geo" in dep_airport:
            event.add("geo", (
                dep_airport["geo"]["latitude"],
                dep_airport["geo"]["longitude"]
            ))

        dep_country = chained_get(dep_airport, "address", "addressCountry")
        dep_location = "".join([
            f"Terminal {dep_terminal}, " if dep_terminal else "",
            dep_airport_name or "",
            f" ({dep_airport_iata})" if dep_airport_iata else "",
            f", {dep_country}" if dep_country else ""
        ])
        event.add("location", dep_location)
    else:
        dep_airport_name = None
        dep_airport_iata = None

    arr_airport_name = chained_get(res_for, "arrivalAirport", "name")
    arr_airport_iata = chained_get(res_for, "arrivalAirport", "iataCode")
    name = "".join([
        "Flight",
        f" {flight_iata}" if flight_iata else "",
        ": ",
        airport_repr(dep_airport_name, dep_airport_iata) or "",
        " to ",
        airport_repr(arr_airport_name, arr_airport_iata)
    ])
    event.add("summary", name)

    event.add("dtstart", datetime.fromisoformat(res_for["departureTime"]["@value"]).astimezone(utc))

    # Output of KItinerary should always have start time but not necessarily end time
    arr_time_str = chained_get(res_for, "arrivalTime", "@value")
    if arr_time_str:
        event.add("dtend", datetime.fromisoformat(arr_time_str).astimezone(utc))

    res_num = reservation_data.get("reservationNumber")
    if res_num:
        event.add("description", f"{name}\nReservation number: {res_num}")

    return event


parsers: dict[str, Callable[[dict[str, Any]], Event]] = {
    "FlightReservation": flight_reservation_parser
}


def parse_reservation(reservation_data: dict[str, Any], config: dict[str, Any]) -> Event:
    """Parse a single reservation dict into an :class:`Event`."""
    res_type = reservation_data["@type"]
    parser = parsers.get(res_type, generic_parser)
    event = parser(reservation_data)
    apply_config(event, config, res_type)
    return Event


def add_attendee(event: Event, email_addr: str):
    """Add an email address as an attendee of an :class:`Event` object, modifying it in place."""
    a = vCalAddress(f"MAILTO:{email_addr}")
    a.params["ROLE"] = vText("REQ-PARTICIPANT")
    event.add("attendee", a, encode=0)


def process_email(email: Message, config: dict[str, Any]) -> list[Event]:
    """Process a single email, determining whether it contains one or more relevant events and returning a list of
    :class:`Event` objects if so.
    """
    cmd = build_cmd(config)
    event_dicts = extract(cmd, email.as_bytes())
    return [parse_reservation(d, config) for d in event_dicts]


def process_mailbox(
        mailbox: Mailbox,
        config: dict[str, Any]
) -> Optional[tuple[Calendar, list[dict[str, Union[str, int]]]]]:
    """Process each email in the given mailbox.

    :param mailbox: The :class:`Mailbox` to iterate for messages to process.
    :param config: A dict containing configuration options (parsed from a config file).
    :return: A tuple containing:
        0. a :class:`Calendar` containing all events found in the mailbox.
        1. details of the events that were found.
    """

    events = []
    details = []
    for msg in mailbox:
        new_events = process_email(msg, config)
        events.extend(new_events)
        if new_events:
            details.append({
                "date": msg.get("Date"),
                "from": msg.get("From"),
                "subject": msg.get("Subject"),
                "num_events": len(new_events)
            })

    cal = Calendar()
    for e in events:
        cal.add_component(e)
    return cal, details


def get_argparser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="eml2cal",
        description="Generate calendar events from emails"
    )
    parser.add_argument("-c", "--config", metavar="PATH", help="Path to config file to use.",
                        default=platformdirs.user_config_dir("eml2cal"))
    return parser


def main():
    parser = get_argparser()
    ns = parser.parse_args()
    try:
        with open(ns.config, "rb") as f:
            config = toml.load(f)
    except (OSError, ValueError) as e:
        logging.critical(f"Could not load config file at {ns.config}: {e}")
        sys.exit(1)
    missing = 0
    for required in ("command", "maildir"):
        if required not in config:
            logging.critical(f"Required configuration value not found: {required}")
            missing += 1
    if missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
