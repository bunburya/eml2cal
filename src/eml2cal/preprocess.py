import logging
from email.message import EmailMessage
from typing import Any

from eml2cal.utils import chained_get


def preprocess_email(email: EmailMessage, config: dict[str, Any]):
    """Perform some pre-processing on an email before extracting data from it, modifying the email in-place."""
    headers = chained_get(config, "preprocess", "headers", default={})
    for copy_from in headers:
        if copy_from in email:
            copy_to = headers[copy_from]
            logging.debug(f"Replacing header `{copy_to}` with content of `{copy_from}`")
            email.replace_header(copy_to, email[copy_from])
