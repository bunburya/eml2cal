from datetime import date
from typing import Callable, Any, Optional

from icalendar import Event, Alarm, vCalAddress, vText
from pytz import utc

from eml2cal.config import get_res_conf_option
from eml2cal.schema_org import parse_datetime
from eml2cal.utils import parse_duration, chained_get, airport_repr


def generic_reservation_to_ical_event(reservation: dict[str, Any]) -> Optional[Event]:
    """Convert a dict representing a schema.org Reservation to an iCalendar event. This function will generally be
    called by a Reservation type-specific converter function to generate a iCalendar event object to use as a starting
    point. It should only be called directly where no Reservation-specific converter is available.

    :param reservation: A dict corresponding to a schema.org Reservation (as constructed from the JSON-LD produced
        by KItinerary).
    :return: An :class:`Event` object containing the key details.
    """
    res_for = reservation["reservationFor"]
    event = Event()
    # Assume that reservationFor is of type Event (technically it could be any Thing, but I believe KItinerary will
    # always produce an Event)
    if "name" in res_for:
        event.add("summary", res_for["name"])
    if "startDate" in res_for:
        event.add("dtstart", parse_datetime(res_for["startDate"]))
    if "endDate" in res_for:
        event.add("dtend", parse_datetime(res_for["endDate"]))
    return event


def flight_reservation_to_ical_event(reservation_data: dict[str, Any]) -> Optional[Event]:
    """Extract details from a dict representing a FlightReservation.

    :param reservation_data: A dict corresponding to a schema.org FlightReservation (as constructed from the JSON-LD
        produced by KItinerary).
    :return: An :class:`Event` object containing the key details.
    """
    event = generic_reservation_to_ical_event(reservation_data)
    res_for = reservation_data["reservationFor"]

    if dep_time := res_for.get("departureTime"):
        event.add("dtstart", parse_datetime(dep_time))
    elif dep_day := res_for.get("departureDay"):
        event.add("dtstart", date.fromisoformat(dep_day))
    else:
        return

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
        f" to ",
        airport_repr(arr_airport_name, arr_airport_iata) or "[unknown]"
    ])
    event.add("summary", name)

    if "arrivalTime" in res_for:
        event.add("dtend", parse_datetime(res_for["arrivalTime"]).astimezone(utc))

    res_num = reservation_data.get("reservationNumber")
    if res_num:
        event.add("description", f"{name}\nReservation number: {res_num}")

    return event


converters: dict[str, Callable[[dict[str, Any]], Optional[Event]]] = {
    "FlightReservation": flight_reservation_to_ical_event
}


def reservation_to_ical_event(reservation_data: dict[str, Any], config: dict[str, Any]) -> Event:
    """Parse a single reservation dict into an :class:`Event`."""
    res_type = reservation_data["@type"]
    parser = converters.get(res_type, generic_reservation_to_ical_event)
    event = parser(reservation_data)
    if event:
        augment_event(event, config, res_type)
    return event


def add_attendee(event: Event, email_addr: str):
    """Add an email address as an attendee of an :class:`Event` object, modifying it in place."""
    a = vCalAddress(f"MAILTO:{email_addr}")
    a.params["ROLE"] = vText("REQ-PARTICIPANT")
    event.add("attendee", a, encode=0)


def augment_event(event: Event, config: dict[str, Any], reservation_type: str):
    """Apply options specified in the given config (eg, alarms, default duration, etc) to the given event, modifying
    it in place.

    :param event: :class:`Event` to modify.
    :param config: A dict containing configuration options, parsed from an appropriate TOML file.
    :param reservation_type: The type of reservation that `event` is referring to (per the schema.org ontology).
    """

    # Apply global config options first

    for a in get_res_conf_option(config, "attendees", reservation_type, []):
        add_attendee(event, a)

    # Then config options that are specific to reservation type

    # Add default duration
    if ((not (event.get("dtend") or event.get("duration")))
            and (dur := get_res_conf_option(config, "default_duration", reservation_type))):
        event.add("duration", parse_duration(dur))

    # Append categories
    if cats := get_res_conf_option(config, "categories", reservation_type):
        if existing := event.pop("categories"):
            existing_set = set(existing.cats)
            for c in cats:
                if c not in existing_set:
                    existing.cats.append()
            event.add("categories", existing.cats)

    # Add alarms
    if alarms := get_res_conf_option(config, "alarms", reservation_type):
        for dur in alarms:
            a = Alarm()
            a.add("action", "audio")
            a.add("trigger", parse_duration(dur) * -1)
            event.add_component(a)


def event_is_valid(event: Event) -> bool:
    """Determine whether an event has enough information to be useful (eg, summary and start time)."""
    return ("dtstart" in event) and ("summary" in event)
