import logging
from typing import Any, Optional

from eml2cal.utils import chained_get

try:
    import tomllib as toml
except ImportError:
    import tomli as toml

"""Functions for loading and basic validation of configuration."""


class ConfigError(Exception):
    """There is some issue with the configuration file."""
    pass


def get_config(fpath) -> dict[str, Any]:
    """Load a configuration from a TOML file."""
    try:
        with open(fpath, "rb") as f:
            return toml.load(f)
    except (OSError, ValueError) as e:
        logging.critical(f"Could not load config file at {fpath}: {e}")
        raise e


def missing_config(config: dict[str, Any]) -> list[str]:
    """Verify that a dict parsed from a config file contains at least the required options.

    :return: A list of strings describing the missing values. If empty, the config is adequate.
    """
    missing = []
    if "command" not in config:
        missing.append("`command`")
    input_conf = config.get("input", {})
    if ("maildir" not in input_conf) and ("mbox" not in input_conf):
        missing.append("`input.maildir` or `input.mbox`")
    return missing


def validate_config(config: dict[str, Any]):
    """Verify that a dict parsed from a config file contains at least the required options.

    :raise ConfigError: If there are critical errors encountered in the configuration.
    """
    errors = 0
    if "command" not in config:
        logging.critical("`command` must be specified in configuration file.")
        errors += 1
    input_conf = config.get("input", {})
    if ("maildir" not in input_conf) and ("mbox" not in input_conf):
        logging.critical("`input.mdir` or `input.mbox` must be specified in configuration file.")
        errors += 1
    if errors:
        raise ConfigError(f"{errors} found in configuration file. Check logs for details.")


def get_res_conf_option(config: dict[str, Any], key: str, res_type: str, default: Optional[Any] = None) -> Any:
    """Get a reservation post-processing configuration option, searching first for a value specified under the section
    for the relevant reservation type and then for a value specified under the general "postprocess" section.

    :param config: The config dict.
    :param key: The name of the configuration option you are searching for.
    :param res_type: The type of the relevant reservation.
    :param default: Value to return if no configured option is found.
    """
    return chained_get(
        config,
        "postprocess", res_type, key,
        default=chained_get(
            config,
            "postprocess", key,
            default=default
        )
    )
