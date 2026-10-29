"""The demo service's fallbacks (review #11 order 5): off, out of budget, not on the allow-list.
No model calls: every path here returns a recorded run before a live one could start. Needs
fastapi (the service image has it): `uv run --with fastapi --with httpx pytest tests/test_service.py`."""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

APP = Path(__file__).resolve().parent.parent / "service" / "app.py"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for k in ("DEMO_ENABLED", "DEMO_TOTAL_USD", "DEMO_DAILY_USD", "DEMO_PASSCODE"):
        monkeypatch.delenv(k, raising=False)
    spec = importlib.util.spec_from_file_location("demo_app", APP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # fresh module: fresh in-memory caps

    def no_live(case=None):  # noqa: ANN001, ANN202, ARG001
        raise AssertionError("a live run started")

    mod._live = no_live
    mod._isolation = lambda: "nobody"  # the caps are what these tests check
    mod.app.state.mod = mod  # tests swap module functions through the app
    return TestClient(mod.app)


def test_off_returns_a_labelled_recorded_run(client: TestClient) -> None:
    j = client.post("/run").json()
    assert j["recorded"] is True and j["reason"] == "live runs are disabled"


def test_total_budget_used_up(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_ENABLED", "true")
    monkeypatch.setenv("DEMO_TOTAL_USD", "0")
    j = client.post("/run").json()
    assert j["recorded"] is True and "total budget" in j["reason"]


def test_daily_budget_used_up(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_ENABLED", "true")
    monkeypatch.setenv("DEMO_DAILY_USD", "0")
    j = client.post("/run").json()
    assert j["recorded"] is True and "today's demo budget" in j["reason"]


def test_case_not_on_the_allow_list(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_ENABLED", "true")
    j = client.post("/run", json={"case": "../../etc/passwd"}).json()
    assert j["recorded"] is True and "allow-list" in j["reason"]


def test_live_run_needs_the_passcode(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_ENABLED", "true")
    monkeypatch.setenv("DEMO_PASSCODE", "open-sesame")
    for body in ({}, {"passcode": "wrong"}):
        j = client.post("/run", json=body).json()
        assert j["recorded"] is True and "passcode" in j["reason"]


def test_reverify_lists_stored_candidates(client: TestClient) -> None:
    cases = client.get("/reverify").json()["cases"]
    assert len(cases) == 20
    assert all(v["verified"] == "verified" for v in cases.values())
    assert sum("rejected" in v for v in cases.values()) >= 10


def test_reverify_rejects_unknown_inputs(client: TestClient) -> None:
    assert "error" in client.post("/reverify", json={"candidate": "mine"}).json()
    assert "error" in client.post("/reverify", json={"case": "../../etc/passwd"}).json()


def test_reverify_runs_the_gate_without_a_passcode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_PASSCODE", "open-sesame")
    calls = []
    mod = client.app.state.mod
    mod._reverify = lambda case, which: calls.append((case, which)) or {"verdict": "verified"}
    j = client.post("/reverify", json={"candidate": "rejected"}).json()
    assert j == {"verdict": "verified"} and calls[0][1] == "rejected"
    for _ in range(5):
        client.post("/reverify")
    assert "cap" in client.post("/reverify").json()["error"]


def test_no_live_run_without_isolation(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_ENABLED", "true")
    client.app.state.mod._isolation = lambda: "setpriv: setresuid failed: Operation not permitted"
    j = client.post("/run").json()
    assert j["recorded"] is True and "isolation" in j["reason"]
    assert "isolation" in client.get("/healthz").json()
