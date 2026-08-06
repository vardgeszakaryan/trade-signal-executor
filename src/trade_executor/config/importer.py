import json
import re
from pathlib import Path

import yaml

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def all_config_import(
    directory_path: str | Path, change_vals: bool = False, **kwargs
) -> dict[str, dict]:
    if isinstance(directory_path, str):
        directory_path = Path(directory_path)

    if directory_path.is_file():
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
    """Load a single YAML/JSON config file and optionally interpolate placeholders.

    Args:
        config_path: Path to the config file.
        change_vals: Whether to interpolate ``{key}`` placeholders with *kwargs*.
        **kwargs: Substitution values for placeholders.

    Returns:
        Parsed dict, or *None* if the file is empty.

    Raises:
        ValueError: If *config_path* is a directory, does not exist, or has
            an unsupported extension.
    """
    if config_path.is_dir():
        raise ValueError("Given config path is a directory.")

    if not config_path.exists():
        raise ValueError("Given config file doesn't exist.")

    file_type = config_path.suffix[1:].lower()

    if not _FORMAT_REGISTRY.get(file_type):
        raise ValueError("Given config file is not supported.")

    content = config_path.read_text()

    if change_vals:
        try:
            content = content.format(**kwargs)
        except KeyError:
            # Only replace placeholders for which we have values;
            # leave unresolved placeholders intact.
            def _safe_substitute(match: re.Match) -> str:
                key = match.group(1)
                return kwargs.get(key, match.group(0))

            content = _PLACEHOLDER_RE.sub(_safe_substitute, content)

    return _FORMAT_REGISTRY[file_type](content)


def _load_yaml(content: str) -> dict:
    return yaml.safe_load(content)


def _load_json(content: str) -> dict:
    return json.loads(content)


_FORMAT_REGISTRY = {"yaml": _load_yaml, "yml": _load_yaml, "json": _load_json}

