"""A tiny invoice assistant built on the library. Run: python examples/invoice_assistant.py

The agent's plan is fixed so it runs anywhere with no API key. Before anything risky it asks
you in the terminal; pressing Enter, or having no terminal, means no.
"""

from oversight import ActionBlocked, ActionDeferred, Oversight

guard = Oversight()
guard.register_tool("find_invoice", category="read", blast_radius="self")  # our own tool: reading is safe


def ask(check):
    print(f"  ? {check.summary}")
    try:
        return input(f"    Approve {check.action.tool} {check.action.params}? [y/N] ").strip().lower() == "y"
    except EOFError:
        return False


@guard.protect(ask=ask)
def find_invoice(number: str) -> str:
    return f"{number} from Acme Supplies, $420, due Friday"


@guard.protect(ask=ask)
def pay_invoice(vendor: str, amount: float) -> str:
    return f"paid ${amount:,.0f} to {vendor}"


@guard.protect(ask=ask)
def update_vendor(vendor: str, bank_account: str) -> str:
    return f"saved new bank details for {vendor}"


plan = [
    (find_invoice, {"number": "INV 2214"}),
    (pay_invoice, {"vendor": "Acme Supplies", "amount": 420}),
    (update_vendor, {"vendor": "Acme Supplies", "bank_account": "GB29 NWBK 6016 1331 9268 19"}),
    (pay_invoice, {"vendor": "Acme Supplies", "amount": 18500}),
]

for tool, args in plan:
    print(f"{tool.__name__} {args}")
    try:
        print(f"  done: {tool(**args)}")
    except ActionDeferred as e:
        print(f"  waiting: {e.check.summary}")
    except ActionBlocked as e:
        print(f"  not run: {'you said no' if e.check.needs_person else e.check.summary}")
