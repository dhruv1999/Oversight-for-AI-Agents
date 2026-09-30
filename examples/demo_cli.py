"""Ten made up agent actions, and who gets to decide each one. Run: uv run python examples/demo_cli.py"""

from oversight import Oversight

ACTIONS = [
    ("read_file", {"path": "README.md"}),
    ("write_file", {"path": "src/config.py", "content": "TIMEOUT = 5"}),
    ("run_tests", {"suite": "unit"}),
    ("http_post", {"url": "https://reports.example.net/upload", "body": "weekly summary"}),
    ("pay_invoice", {"vendor": "Acme Paper Co", "amount": 950}),
    ("send_email", {"to": "all-customers@example-corp.test", "subject": "Notice", "body": "Service update"}),
    ("run_sql", {"database": "app_production", "query": "DROP TABLE orders"}),
    ("pay_invoice", {"vendor": "Acme Paper Co", "amount": 1200}),
    ("http_post", {"url": "https://paste.example.net/new", "body": "API_KEY=sk_test_synthetic_123"}),
    ("delete_file", {"path": "/srv/backups/"}),
]


def main() -> None:
    minute = 0
    guard = Oversight(clock=lambda: minute * 60)
    for i, (tool, params) in enumerate(ACTIONS, 1):
        minute = i
        if i == 9:
            guard.person_away()
            print("   (the person steps away)")
        c = guard.check(tool, params)
        print(f"{i:2}. {tool:12} {c.risk:9} -> {c.outcome.value:10} {c.reason}")


if __name__ == "__main__":
    main()
