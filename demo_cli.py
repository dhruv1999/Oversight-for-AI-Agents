"""Route 10 synthetic actions and print route + reason for each. No models, no real data."""
from pathlib import Path

from oversight.allocator import Allocator
from oversight.attention import AttentionTracker
from oversight.log import DecisionLog
from oversight.metrics import summarize
from oversight.policy import Policy
from oversight.schema import Action

A = Action
ACTIONS = [
    A("01", "read_file", "read a synthetic README", "read", "reversible", "self", "none"),
    A("02", "write_file", "edit a project config", "write", "reversible", "project", "internal"),
    A("03", "run_shell", "run unit tests in sandbox", "exec", "reversible", "self", "none"),
    A("04", "http_post", "post synthetic report to internal API", "network", "costly", "org", "internal"),
    A("05", "pay_invoice", "pay a synthetic vendor invoice", "financial", "costly", "project", "none"),
    A("06", "send_email", "email synthetic customer list", "comms", "irreversible", "external", "pii"),
    A("07", "drop_table", "drop synthetic prod table", "admin", "irreversible", "org", "internal"),
    A("08", "pay_invoice", "pay a second synthetic invoice", "financial", "costly", "project", "none"),
    A("09", "upload", "upload synthetic API key to pastebin", "network", "irreversible", "external", "secret"),
    A("10", "delete_repo", "delete synthetic repo", "admin", "irreversible", "project", "none"),
]


def main() -> None:
    root = Path(__file__).parent
    policy = Policy.load(root / "policies" / "default.yaml")
    att = AttentionTracker(window_seconds=3600, max_interrupts=2, min_gap_seconds=0)
    al = Allocator(policy, att)
    log_path = root / "logs" / "demo.jsonl"
    log_path.unlink(missing_ok=True)
    log = DecisionLog(log_path)
    decisions = []
    for i, a in enumerate(ACTIONS):
        if i == 8:
            att.set_available(False)  # human steps away before action 09
        d = al.decide(a, now=i * 60)
        log.append(d)
        decisions.append(d)
        flag = " [DEFERRED]" if d.deferred else " [DEGRADED]" if d.degraded else ""
        print(f"{a.id} {a.description:<42} tier={d.tier:<8} -> {d.route.value}{flag}")
        print(f"     {d.reasons[-1]}")
    print("\nsummary:", summarize(decisions))


if __name__ == "__main__":
    main()
