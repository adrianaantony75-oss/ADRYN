import psycopg
from click.testing import CliRunner

from adryn import cli as cli_module
from adryn.settings import project_root


def test_source_and_installed_project_roots(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "pyproject.toml").touch()
    assert project_root(checkout / "src" / "adryn" / "settings.py") == checkout
    monkeypatch.chdir(checkout)
    installed = tmp_path / "environment" / "site-packages" / "adryn" / "settings.py"
    assert project_root(installed) == checkout


def test_database_check_requires_project_env(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("ADRYN_DATABASE_URL", "postgresql://ambient:private@localhost/adryn")
    result = CliRunner().invoke(cli_module.cli, ["verify-db"])
    assert result.exit_code == 1
    assert "Project .env is absent" in result.output
    assert "private" not in result.output


def test_database_check_sanitizes_connection_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_module, "PROJECT_ROOT", tmp_path)
    secret = "synthetic-secret-for-test"
    (tmp_path / ".env").write_text(
        f"ADRYN_DATABASE_URL=postgresql://test:{secret}@localhost/adryn\n"
    )

    def fail_connect(url, **kwargs):
        assert url == f"postgresql://test:{secret}@localhost/adryn"
        assert kwargs["connect_timeout"] == 5
        raise psycopg.OperationalError(f"Connection refused for {url}")

    monkeypatch.setattr(cli_module.psycopg, "connect", fail_connect)
    result = CliRunner().invoke(cli_module.cli, ["verify-db"])
    assert result.exit_code == 1
    assert "Connection details are withheld" in result.output
    assert secret not in result.output
