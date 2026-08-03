import json
import re
from pathlib import Path

import yaml


def all_config_import(
    directory_path: str | Path, change_vals: bool = False, **kwargs
) -> dict[str, dict]:
    if isinstance(directory_path, str):
        directory_path = Path(directory_path)

    if directory_path.is_file():
        # TODO ADD LOGGING
        raise ValueError("Given path is not a directory")

    final_config = {}

    for item in directory_path.iterdir():
        if item.is_dir():
            continue
        config = import_config(item, change_vals, **kwargs)

        if config:
            final_config[item.stem.lower()] = config

    return final_config


def import_config(config_path: Path, change_vals: bool = False, **kwargs) -> dict | None:
    """
    @args
        config_path: Path -> Config path that should be loaded
        change_vals: bool -> Whether to change loaded text before parsing or not
        **kwargs: Any -> Used only for parameters that need to be changed

    @returns: (dict | none) -> dict if import was successfull, None otherwise

    @raises
        ValueError: if the path is a directory, does not exist, or the
            file extension is not a supported config format (yaml/yml/json).
    """
    if config_path.is_dir():
        # TODO add logg
        raise ValueError("Given config path is a directory.")

    if not config_path.exists():
        # TODO add logg
        raise ValueError("Given config file doesn't exist.")

    file_type = config_path.suffix[1:].lower()

    if not __registry__.get(file_type):
        # TODO add logg
        raise ValueError("Given config file is not supported.")

    content = config_path.read_text()

    if change_vals:
        # Safe format that leaves missing placeholders unchanged
        try:
            content = content.format(**kwargs)
        except KeyError:
            # If any placeholders are missing, fall back to substitution that
            # only replaces keys which are actually available in kwargs.
            def safe_format(match):
                key = match.group(1)
                return kwargs.get(key, match.group(0))

            content = re.sub(r"\{(\w+)\}", safe_format, content)

    return __registry__[file_type](content)


def import_yaml(content: str) -> dict:
    return yaml.safe_load(content)


def import_json(content: str) -> dict:
    return json.loads(content)


__registry__ = {"yaml": import_yaml, "yml": import_yaml, "json": import_json}
