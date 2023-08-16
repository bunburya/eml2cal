from collections import OrderedDict
from datetime import date, datetime
from typing import Callable, Any, Optional

from icalendar import Event, Alarm, vCalAddress, vText, vGeo
from pytz import utc

from eml2cal.config import get_res_conf_option
from eml2cal.schema_org import parse_datetime
from eml2cal.utils import parse_duration, chained_get, airport_repr, augment_description


def get_times(reservation: dict[str, Any]) -> tuple[Optional[datetime], Optional[datetime]]:
    """Get the start and end time of a reservation, first checking the reservation dict itself
    and then checking the event dict.
    """

    found = {"start": None, "end": None}
    for s in ("start", "end"):
        for k in (s + "Time", s + "Date"):
            for d in (reservation, reservation.get("reservationFor", {})):
                if (f := d.get(k)) and not found.get(s):
                    found[s] = parse_datetime(f)
                    if found["start"] and found["end"]:
                        break
    return found["start"], found["end"]


def get_location(reservation: dict[str, Any]) -> tuple[Optional[str], Optional[tuple[float, float]]]:
    """Get the location of a reservation, by checking its ``reservationFor`` attribute.

    :return: A tuple containing the location's address and coordinates (in each case, if present)."""
    address_dict = chained_get(
        reservation,
        "reservationFor.address",
        chained_get(reservation, "reservationFor.location.address")
    )
    if address_dict:
        address_lines = []
        for k in ("streetAddress", "addressLocality", "postalCode", "addressCountry"):
            if k in address_dict:
                address_lines.append(address_dict[k])
        address = ". ".join(address_lines)
    else:
        address = None
    geo_dict = chained_get(reservation, "reservationFor.geo", chained_get(reservation, "reservationFor.location.geo"))
    if geo_dict:
        geo = geo_dict["latitude"], geo_dict["longitude"]
    else:
        geo = None
    return address, geo


def get_action_urls(reservation: dict[str, Any]) -> Optional[OrderedDict[str, str]]:
    """Get URLs for performing certain actions on the reservation."""

    if "potentialAction" not in reservation:
        return None
    actions = OrderedDict()
    for a in reservation["potentialAction"]:
        if "target" in a:
            actions[a["@type"]] = a["target"]
    return actions


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

    dtstart, dtend = get_times(reservation)
    if dtstart:
        event.add("dtstart", dtstart)
    if dtend:
        event.add("dtend", dtend)

    location, geo = get_location(reservation)
    if location:
        event.add("location", location)
    if geo:
        event.add("geo", geo)

    if "name" in res_for:
        event.add("summary", res_for["name"])

    desc_lines = []
    if res_num := reservation.get("reservationNumber"):
        desc_lines.append(f"Reservation number: {res_num}")
    actions = get_action_urls(reservation)
    if actions:
        for a in actions:
            aname = a.rstrip("Action")
            url = actions[a]
            desc_lines.append(f"{aname}: {url}")
    if desc_lines:
        event.add("description", "\n".join(desc_lines))

    return event


def flight_reservation_to_ical_event(reservation: dict[str, Any]) -> Optional[Event]:
    """Extract details from a dict representing a FlightReservation.

    :param reservation: A dict corresponding to a schema.org FlightReservation (as constructed from the JSON-LD
        produced by KItinerary).
    :return: An :class:`Event` object containing the key details.
    """
    event = generic_reservation_to_ical_event(reservation)
    res_for = reservation["reservationFor"]

    if "dtstart" not in event:
        if dep_time := res_for.get("departureTime"):
            event.add("dtstart", parse_datetime(dep_time))
        elif dep_day := res_for.get("departureDay"):
            event.add("dtstart", date.fromisoformat(dep_day))
        else:
            return
    if ("dtend" not in event) and ("arrivalTime" in res_for):
        event.add("dtend", parse_datetime(res_for["arrivalTime"]).astimezone(utc))

    airline_iata = res_for.get("airline", {}).get("iataCode", "")
    flight_iata = airline_iata + res_for.get("flightNumber")

    dep_airport = res_for.get("departureAirport")
    if dep_airport:
        dep_airport_name = dep_airport.get("name")
        dep_airport_iata = dep_airport.get("iataCode")
        dep_terminal = res_for.get("departureTerminal")
        if "geo" in dep_airport:
            event["geo"] = vGeo((dep_airport["geo"]["latitude"], dep_airport["geo"]["longitude"]))

        dep_country = chained_get(dep_airport, "address.addressCountry")
        dep_location = "".join([
            f"Terminal {dep_terminal}, " if dep_terminal else "",
            dep_airport_name or "",
            f" ({dep_airport_iata})" if dep_airport_iata else "",
            f", {dep_country}" if dep_country else ""
        ])
        event["location"] = vText(dep_location)
    else:
        dep_airport_name = None
        dep_airport_iata = None

    arr_airport_name = chained_get(res_for, "arrivalAirport.name")
    arr_airport_iata = chained_get(res_for, "arrivalAirport.iataCode")
    name = "".join([
        "Flight",
        f" {flight_iata}" if flight_iata else "",
        ": ",
        airport_repr(dep_airport_name, dep_airport_iata) or "",
        f" to ",
        airport_repr(arr_airport_name, arr_airport_iata) or "[unknown]"
    ])
    event["summary"] = vText(name)

    res_num = reservation.get("reservationNumber")
    if res_num:
        event.add("description", f"{name}\nReservation number: {res_num}")

    return event


def lodging_reservation_to_ical_event(reservation: dict[str, Any]) -> Optional[Event]:
    """Extract details from a dict representing a LodgingReservation.

    :param reservation: A dict corresponding to a schema.org LodgingReservation (as constructed from the JSON-LD
        produced by KItinerary).
    :return: An :class:`Event` object containing the key details.
    """
    event = generic_reservation_to_ical_event(reservation)
    if not "dtstart" in event:
        if checkin := reservation.get("checkinTime"):
            event.add("dtstart", parse_datetime(checkin))
        else:
            return
    if ("dtend" not in event) and (checkout := reservation.get("checkoutTime")):
        event.add("dtend", parse_datetime(checkout))
    return event


converters: dict[str, Callable[[dict[str, Any]], Optional[Event]]] = {
    "FlightReservation": flight_reservation_to_ical_event,
    "LodgingReservation": lodging_reservation_to_ical_event
}


def reservation_to_ical_event(reservation: dict[str, Any], config: dict[str, Any]) -> Event:
    """Parse a single reservation dict into an :class:`Event`."""
    res_type = reservation["@type"]
    parser = converters.get(res_type, generic_reservation_to_ical_event)
    event = parser(reservation)
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
