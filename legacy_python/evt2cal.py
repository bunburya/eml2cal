import json
from datetime import datetime, timedelta
from typing import Optional, Any, Collection
from pytz import utc
from ics import Calendar, Event
from ics.alarm.base import BaseAlarm
from ics.alarm.utils import get_type_from_action


config = {
    "alarm_action": "DISPLAY",
    "alarms": {
        "FlightReservation": [
            timedelta(hours=3)
        ]
    },
    "categories": {
        "FlightReservation": ["Travel"]
    }
}

def get_alarms(event_type: str) -> Optional[list[BaseAlarm]]:
    """Return a list of :class:`BaseAlarm` objects based on the event type."""
    triggers = config.get("alarms", {}).get(event_type)
    if not triggers:
        return None
    cls = get_type_from_action(config["alarm_action"])
    return [cls(a) for a in triggers]


def flight_to_event(data: dict[str, Any]) -> Event:
    """Parse a single flight reservation and return a calendar event.

    :param data: A dict, in the JSON-LD format returned by kitinerary-extractor,
        representing a single flight reservation.
    """
    res = data["reservationFor"]

    airline_iata = res["airline"]["iataCode"]
    flight_iata = airline_iata + res["flightNumber"]

    dep_airport_name = res["departureAirport"]["name"]
    dep_airport_iata = res["departureAirport"]["iataCode"]
    dep_terminal = res.get("departureTerminal")
    dep_coords = (
        res["departureAirport"]["geo"]["latitude"],
        res["departureAirport"]["geo"]["longitude"]
    )
    dep_country = res["departureAirport"]["address"]["addressCountry"]
    dep_location = f"{dep_airport_name} Airport ({dep_airport_iata}), {dep_country}"
    if dep_terminal:
        dep_location = f"Terminal {dep_terminal}, " + dep_location

    arr_airport_name = res["arrivalAirport"]["name"]
    arr_airport_iata = res["arrivalAirport"]["iataCode"]

    dep_time_utc = datetime.fromisoformat(res["departureTime"]["@value"]).astimezone(utc)
    arr_time_utc = datetime.fromisoformat(res["arrivalTime"]["@value"]).astimezone(utc)

    name = (
        f"Flight {flight_iata}: "
        f"{dep_airport_name} ({dep_airport_iata}) to "
        f"{arr_airport_name} ({arr_airport_iata})"
    )

    res_num = data["reservationNumber"]

    desc = name + f"\nReservation number: {res_num}"

    return Event(
        name=name,
        begin=dep_time_utc,
        end=arr_time_utc,
        description=desc,
        created=datetime.utcnow(),
        location=dep_location,
        geo=dep_coords,
        alarms=get_alarms("FlightReservation")
    )


parsers = {
    "FlightReservation": flight_to_event
}


def dedupe_events(events: Collection[Event]) -> list[Event]:
    """De-duplicate a collection of events by removing those with the same start and end
    times as existing events.
    
    :return: A list of events with duplicates removed.
    """

    key_details = set()
    deduped = []
    for e in events:
        k = (e.begin, e.end)
        if k not in key_details:
            deduped.append(e)
            key_details.add(k)
    return deduped


def events_to_ical(data: list[dict[str, Any]]) -> list[Event]:
    """Parse a list of flight reservations into a list of calendar events.

    :param data: A list of dicts, in the JSON-LD format returned by kitinerary-extractor,
        representing multiple flight reservations.
    """
    events = []
    for d in data:
        evt_type = d["@type"]
        parser = parsers.get(evt_type)
        if parser is None:
            raise ValueError(f"No parser found for event of type {evt_type}.")
        events.append(parser(d))
    events = dedupe_events(events)
    return Calendar(events=events)


def main():
    from sys import stdin
    data = json.load(stdin)
    print(events_to_ical(data).serialize())


if __name__ == "__main__":
    main()

