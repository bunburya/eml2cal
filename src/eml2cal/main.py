import logging
import os.path
import sys

import platformdirs
from argparse import ArgumentParser
from datetime import datetime

from icalendar import Event, Calendar

from eml2cal.config import get_config
from eml2cal.mail import get_mailbox
from eml2cal.cal_utils import save_events
from eml2cal.process import process_emails, from_files
from eml2cal.summary import Summary, send_report
from eml2cal.utils import chained_get

logger = logging.getLogger()


def get_argparser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="eml2cal",
        description="Generate calendar events from emails"
    )
    parser.add_argument("-c", "--config", metavar="PATH", help="Path to config file to use.",
                        default=os.path.join(platformdirs.user_config_dir("eml2cal"), "config.toml"))
    parser.add_argument("-t", "--test", action="store_true",
                        help="Print resulting iCalendar file rather than adding to a dictionary.")
    parser.add_argument("-f", "--file", nargs="*",
                        help="Parse emails in given file(s) rather than from mailbox.")
    return parser


def make_calendar(events: list[Event]) -> Calendar:
    """Make a :class:`Calendar` object from a list of :class:`Event`s."""
    cal = Calendar()
    for e in events:
        cal.add_component(e)
    return cal


def main():
    parser = get_argparser()
    ns = parser.parse_args()
    config = get_config(ns.config)
    if not config:
        logger.critical("Could not find configuration file.")
        sys.exit(1)
    root_logger = logging.getLogger()
    if chained_get(config, "logging.debug", default=False):
        root_logger.level = logging.DEBUG
    if log_dir := chained_get(config, "logging.log_dir", default=None):
        log_dir = os.path.expanduser(log_dir)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        log_file = os.path.join(log_dir, datetime.now().isoformat()) + ".log"
        root_logger.addHandler(logging.FileHandler(log_file))
    else:
        root_logger.addHandler(logging.StreamHandler())

    if ns.file:
        emails = from_files(ns.file)
        is_mb = False
    else:
        emails = get_mailbox(config)
        is_mb = True

    summary = Summary(start_time=datetime.now())
    events = process_emails(emails, config, summary)
    if ns.test:
        print(make_calendar(events).to_ical().decode())
    else:
        save_events(events, config, summary)
        if summary.extracted or summary.conflicts or summary.errors:
            send_report(config, summary)
        if is_mb and chained_get(config, "mailbox.delete_processed_emails", False):
            logging.info("Deleting all emails in mailbox.")
            emails.lock()
            emails.clear()
            emails.close()


if __name__ == "__main__":
    main()
