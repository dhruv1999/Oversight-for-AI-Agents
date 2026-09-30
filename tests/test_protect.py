import asyncio
import inspect

import pytest

from oversight import ActionBlocked, ActionDeferred, Oversight


def make():
    return Oversight(clock=lambda: 1000.0)


def test_low_risk_tool_just_runs():
    guard = make()

    @guard.protect()
    def read_file(path: str) -> str:
        """Read a file."""
        return f"contents of {path}"

    assert read_file("README.md") == "contents of README.md"


def test_needs_person_without_ask_is_refused_with_a_readable_reason():
    guard = make()
    ran = []

    @guard.protect()
    def pay_invoice(vendor: str, amount: float) -> str:
        ran.append(1)
        return "paid"

    with pytest.raises(ActionBlocked) as e:
        pay_invoice("Acme", 420)
    assert not ran and "pay_invoice was not run" in str(e.value) and e.value.check.needs_person


def test_ask_callback_approves_or_denies():
    guard = make()
    asked = []

    def ask(check):
        asked.append(check.action.params)
        return check.action.params["amount"] < 1000

    @guard.protect(ask=ask)
    def pay_invoice(vendor: str, amount: float = 0.0) -> str:
        return f"paid {amount}"

    assert pay_invoice("Acme", amount=420) == "paid 420"
    assert asked == [{"vendor": "Acme", "amount": 420}]


def test_denied_by_person():
    guard = Oversight(clock=iter(range(0, 10**6, 100)).__next__)

    @guard.protect(ask=lambda c: False)
    def pay_invoice(vendor: str, amount: float) -> str:
        return "paid"

    with pytest.raises(ActionBlocked):
        pay_invoice("Acme", 420)


def test_waiting_raises_deferred():
    guard = make()
    guard.person_away()

    @guard.protect(tool="run_sql")
    def query(database: str, query: str) -> str:
        return "ok"

    with pytest.raises(ActionDeferred):
        query("app_production", "DROP TABLE orders")


def test_async_tools_and_signature_is_kept():
    guard = make()

    @guard.protect()
    async def read_file(path: str, encoding: str = "utf8") -> str:
        """Read a file from the project."""
        return path

    assert asyncio.run(read_file("a.txt")) == "a.txt"
    assert list(inspect.signature(read_file).parameters) == ["path", "encoding"]
    assert read_file.__name__ == "read_file" and read_file.__doc__ == "Read a file from the project."
    assert inspect.iscoroutinefunction(read_file)


def test_methods_do_not_leak_self_into_params(tmp_path):
    import json

    guard = Oversight(clock=lambda: 1000.0, log_path=tmp_path / "log.jsonl")

    class Tools:
        @guard.protect(tool="read_file")
        def read(self, path: str) -> str:
            return path

    assert Tools().read("a") == "a"
    logged = json.loads((tmp_path / "log.jsonl").read_text().splitlines()[0])["action"]["params"]
    assert logged == {"path": "a"}
