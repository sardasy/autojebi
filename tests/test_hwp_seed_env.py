import os

from api.hwp_fields import __main__ as cli


def test_seed_cli_reads_local_company_settings_without_overriding_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("COMPANY_NAME=Example\nCOMPANY_ADDRESS=File address\n", encoding="utf-8")
    monkeypatch.delenv("COMPANY_NAME", raising=False)
    monkeypatch.setenv("COMPANY_ADDRESS", "Explicit address")
    monkeypatch.setattr("sys.argv", ["hwp_fields", "seed"])
    observed = []
    monkeypatch.setattr(cli, "seed", lambda: observed.append((os.getenv("COMPANY_NAME"), os.getenv("COMPANY_ADDRESS"))))
    cli.main()
    assert observed == [("Example", "Explicit address")]
