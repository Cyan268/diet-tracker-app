from app.cli import serve_vps


class _ScriptDirectory:
    def get_current_head(self) -> str:
        return "20260916_0014"


def test_vps_launcher_sets_schema_contract_and_execs_one_worker(monkeypatch) -> None:
    executed: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(serve_vps, "preflight", lambda _args: 0)
    monkeypatch.setattr(
        serve_vps.ScriptDirectory,
        "from_config",
        lambda _config: _ScriptDirectory(),
    )
    monkeypatch.setattr(
        serve_vps.os,
        "execvp",
        lambda executable, args: executed.append((executable, args)),
    )

    assert serve_vps.main() == 0
    assert serve_vps.os.environ["NUTRIPILOT_REQUIRED_SCHEMA_REVISION"] == "20260916_0014"
    assert executed == [
        (
            "uvicorn",
            [
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--workers",
                "1",
                "--no-proxy-headers",
                "--no-access-log",
            ],
        )
    ]


def test_vps_launcher_stops_when_preflight_fails(monkeypatch) -> None:
    monkeypatch.setattr(serve_vps, "preflight", lambda _args: 1)
    monkeypatch.setattr(
        serve_vps.os,
        "execvp",
        lambda _executable, _args: (_ for _ in ()).throw(AssertionError("must not exec")),
    )

    assert serve_vps.main() == 1
