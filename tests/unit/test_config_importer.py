import pytest
from pathlib import Path
from trade_executor.config import import_config


# --- Success Cases ---

def test_import_yaml_valid(tmp_path: Path):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("key: value\nnumber: 42")

    result = import_config(yaml_file)
    assert result == {"key": "value", "number": 42}


def test_import_json_valid(tmp_path: Path):
    json_file = tmp_path / "config.json"
    json_file.write_text('{"key": "value", "number": 42}')

    result = import_config(json_file)
    assert result == {"key": "value", "number": 42}


def test_case_insensitive_extension(tmp_path: Path):
    json_file = tmp_path / "config.JSON"
    json_file.write_text('{"status": "ok"}')

    result = import_config(json_file)
    assert result == {"status": "ok"}


# --- Failure & Edge Cases ---

def test_raises_if_path_is_directory(tmp_path: Path):
    # Tests the fixes for path.is_dir()
    with pytest.raises(ValueError, match="Given config path is a directory."):
        import_config(tmp_path)


def test_raises_for_unsupported_extension(tmp_path: Path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('key = "value"')

    with pytest.raises(ValueError, match="Given config file is not supported."):
        import_config(toml_file)


def test_raises_for_file_without_extension(tmp_path: Path):
    no_ext_file = tmp_path / "config"
    no_ext_file.write_text("key: value")

    with pytest.raises(ValueError, match="Given config file is not supported."):
        import_config(no_ext_file)