import os.path
from email.parser import BytesParser
from email.policy import default
from mailbox import Mailbox, Maildir, mbox
from typing import Any


def get_mailbox(config: dict[str, Any]) -> Mailbox:
    """Get a mailbox of the appropriate type."""
    email_factory = BytesParser(policy=default).parse
    input_conf = config["mailbox"]
    if "maildir" in input_conf:
        mdir = os.path.expanduser(input_conf.get("maildir"))
        mb_class = Maildir
    elif "mbox" in input_conf:
        mdir = os.path.expanduser(input_conf.get("mbox"))
        mb_class = mbox
    else:
        mdir = None
    if not mdir:
        raise ValueError("Could not find mailbox configuration option.")
    if not os.path.exists(mdir):
        raise ValueError(f"File or directory does not exist: {mdir}")
    return mb_class(mdir, factory=email_factory, create=False)
