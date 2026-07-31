import json
from pathlib import Path

import yaml


def import_config(config_path: Path) -> dict:
    ## Supported config types
    if config_path.is_dir():
        raise ValueError("Given config path is a directory.")

    if not config_path.exists():
        raise ValueError("Given file doesn't exist.")

    file_type = config_path.suffix[1:].lower()

    if not __registry__.get(file_type):
        raise ValueError("Given config file is not supported.")

    return __registry__[file_type](config_path)


def import_yaml(config_path: Path) -> dict:
    return yaml.safe_load(config_path.read_text())


def import_json(config_path: Path) -> dict:
    return json.loads(config_path.read_text())


__registry__ = {"yaml": import_yaml, "json": import_json}
