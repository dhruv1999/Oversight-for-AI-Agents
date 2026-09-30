"""The README's developer example. Run: uv run python examples/quickstart.py"""

from oversight import Oversight

guard = Oversight()  # default rules, free rule based checker, interrupt budget from the policy

for tool, params in [
    ("run_sql", {"database": "app", "query": "SELECT count(*) FROM orders"}),
    ("pay_invoice", {"vendor": "Acme Paper Co", "amount": 420}),
]:
    print(guard.check(tool, params).explain(), "\n")

guard.person_away()  # the person steps into a meeting
check = guard.check("run_sql", {"database": "app_production", "query": "DROP TABLE orders"})
print(check.explain())
assert check.waiting
