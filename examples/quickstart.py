"""The README's developer example, runnable as is: uv run python examples/quickstart.py"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oversight import Allocator, AttentionTracker, HeuristicSafetyModel, Outcome, OversightGate, Policy, ToolRegistry  # noqa: E402

# 1. Load the rules
policy = Policy.load(ROOT / "policies/default.yaml")
registry = ToolRegistry.load(ROOT / "policies/tools.yaml", policy)
attention = AttentionTracker.from_config(policy.attention)
gate = OversightGate.from_policy(policy, Allocator(policy, attention), HeuristicSafetyModel())


# 2. Call this before your agent runs any tool
def check(call_id, tool, params, description):
    action = registry.to_action(call_id, tool, params, description)
    result = gate.review(action, now=time.time())
    print(f"{tool}: {result.outcome.value} ({result.decision.tier} risk)")
    for reason in result.decision.reasons:
        print("   ", reason)
    return result.outcome


# 3. Try it
check("c1", "run_sql", {"database": "app", "query": "SELECT count(*) FROM orders"}, "Count orders")
check("c2", "pay_invoice", {"vendor": "Acme Paper Co", "amount": 420, "invoice_id": "INV-1"}, "Pay an invoice")
attention.set_available(False)  # the person steps away
outcome = check("c3", "run_sql", {"database": "app_production", "query": "DROP TABLE orders"}, "Clean up")
assert outcome == Outcome.DEFER
