from datetime import datetime
from typing import Union, Any

from dateutil.parser import isoparse
from pytz import timezone

"""Functions for working with the data returned by Kitinerary, generally in dict format representing a Reservation or
Event (or some sub-type) as defined in the schema.org ontology (or the simplified ontology defined by KItinerary).
"""


def parse_datetime(dt_data: Union[str, dict[str, str]]) -> datetime:
    """Sometimes in the output returned by KItinerary a datetime object may be expressed as a string, whereas other
    times it is a dict whose `@value` attribute is a string. It looks like it may be a string where it is UTC. In any
     event, this function handles both cases.
    """
    if isinstance(dt_data, str):
        return isoparse(dt_data)
    elif isinstance(dt_data, dict):
        dt = isoparse(dt_data["@value"])
        if "timezone" in dt_data:
            return dt.astimezone(timezone(dt_data["timezone"]))
    else:
        raise ValueError(f"dt_data must be str or dict, not {type(dt_data)}")


def is_reservation(thing: dict[str, Any]) -> bool:
    """Check if the given dict represents a reservation (as opposed to another thing in the schema.org ontology)."""
    # TODO: Make better by checking against type and also implement for Event.
    return "reservationFor" in thing
