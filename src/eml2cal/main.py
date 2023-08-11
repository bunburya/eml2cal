import logging
import os.path
import sys

import platformdirs
from argparse import ArgumentParser
from datetime import datetime

from eml2cal.config import get_config
from eml2cal.mail import get_mailbox
from eml2cal.calendar import save_events
from eml2cal.process import process_mailbox
from eml2cal.summary import Summary, send_report
from eml2cal.utils import chained_get

logger = logging.getLogger()


def get_argparser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="eml2cal",
        description="Generate calendar events from emails"
    )
    parser.add_argument("-c", "--config", metavar="PATH", help="Path to config file to use.",
                        default=platformdirs.user_config_dir("eml2cal"))
    return parser


def main():
    try:
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

        mb = get_mailbox(config)
        summary = Summary(start_time=datetime.now())
        events = process_mailbox(mb, config, summary)
        save_events(events, config, summary)
        if summary.extracted or summary.conflicts or summary.errors:
            send_report(config, summary)
        if chained_get(config, "mailbox.delete_processed_emails", False):
            logging.info("Deleting all emails in mailbox.")
            mb.lock()
            mb.clear()
            mb.close()
    except Exception as e:
        logger.critical(f"Encountered uncaught exception: {e.with_traceback()}")
        sys.stdout.write(f"Encountered fatal error. Check logs for further details: {e}")
        sys.exit(1)
