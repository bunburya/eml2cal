import json
import os.path
import shlex
import subprocess
from typing import Any

from eml2cal.utils import chained_get

"""Function for interacting with kitinerary-extractor."""


def build_cmd(config: dict[str, Any]) -> list[str]:
    """Generate the command to run to invoke `kitinerary-extractor`."""
    cmd = shlex.split(chained_get(config, "extractor.command", ""))
    if not cmd:
        raise ValueError("Configuration file must specify extractor command to use.")
    if "additional_extractors" in config:
        cmd.extend(["--additional-search-path", os.path.expanduser(config["additional_extractors"])])
    return cmd


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
