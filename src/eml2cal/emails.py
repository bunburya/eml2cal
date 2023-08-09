import os.path
from email.parser import BytesParser
from email.policy import default
from mailbox import Mailbox, Maildir, mbox
from typing import Any


def get_mailbox(config: dict[str, Any]) -> Mailbox:
    """Get a mailbox of the appropriate type."""
    email_factory = BytesParser(policy=default).parse
    input_conf = config["input"]
    if "maildir" in input_conf:
        mdir = input_conf["maildir"]
        mb_class = Maildir
    elif "mbox" in input_conf:
        mdir = input_conf["mbox"]
        mb_class = mbox
    else:
        raise ValueError("Could not find mailbox configuration option.")
    if not os.path.exists(mdir):
        raise ValueError(f"File or directory does not exist: {mdir}")
    return mb_class(mdir, factory=email_factory, create=False)
