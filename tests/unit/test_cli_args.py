"""Tests for the Typer CLI interface."""

from unittest.mock import patch

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


class TestHelpOutput:
    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "monitor" in result.output
        assert "migrate" in result.output

    def test_monitor_help(self):
        result = runner.invoke(app, ["monitor", "--help"])
        assert result.exit_code == 0
        assert "--config-dir" in result.output
        assert "--dry-run" in result.output
        assert "--symbol" in result.output
        assert "--max-lot-size" in result.output
        assert "--log-level" in result.output

    def test_migrate_help(self):
        result = runner.invoke(app, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "--db-path" in result.output


class TestMigrateCommand:
    def test_migrate_creates_db(self, tmp_path):
        db_path = str(tmp_path / "test_migrate.db")
        result = runner.invoke(app, ["migrate", "--db-path", db_path])
        assert result.exit_code == 0
        assert "Migrations applied" in result.output

    def test_migrate_idempotent(self, tmp_path):
        db_path = str(tmp_path / "idempotent.db")
        # Run twice — second should not error
        runner.invoke(app, ["migrate", "--db-path", db_path])
        result = runner.invoke(app, ["migrate", "--db-path", db_path])
        assert result.exit_code == 0


class TestMonitorCommand:
    @patch.dict("os.environ", {"USE_LLM": "false"}, clear=False)
    def test_monitor_no_llm_warns(self, tmp_path):
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        (config_dir / "logger.yaml").write_text("level: INFO\nsink: stdout")
        (config_dir / "trades.yaml").write_text("parser_type: llm\nmax_lot_size: 0.03\ncancel_strategy: manual")

        result = runner.invoke(app, [
            "monitor",
            "--config-dir", str(config_dir),
        ])
        # Should not crash; USE_LLM=false means it just warns
        assert result.exit_code == 0


class TestUnknownCommand:
    def test_unknown_subcommand_fails(self):
        result = runner.invoke(app, ["nonexistent"])
        assert result.exit_code != 0
