from oversight.attention import AttentionTracker


def make(**kw):
    d = dict(window_seconds=100, max_interrupts=2, min_gap_seconds=10)
    d.update(kw)
    return AttentionTracker(**d)


def test_available_initially():
    ok, _ = make().can_interrupt(0)
    assert ok


def test_unavailable_blocks_with_reason():
    t = make()
    t.set_available(False)
    ok, why = t.can_interrupt(0)
    assert not ok and "unavailable" in why


def test_min_gap():
    t = make()
    t.record_interrupt(0)
    ok, why = t.can_interrupt(5)
    assert not ok and "gap" in why
    assert t.can_interrupt(10)[0]


def test_budget_per_window():
    t = make(min_gap_seconds=0)
    t.record_interrupt(0)
    t.record_interrupt(1)
    ok, why = t.can_interrupt(2)
    assert not ok and "budget" in why


def test_budget_recovers_after_window():
    t = make(min_gap_seconds=0)
    t.record_interrupt(0)
    t.record_interrupt(1)
    assert t.can_interrupt(100)[0]  # first aged out
    assert t.interrupts_in_window(100) == 1


def test_availability_only_gate_ignores_budget():
    t = make(min_gap_seconds=0)
    t.record_interrupt(0)
    t.record_interrupt(1)
    assert t.is_available()


def test_from_config():
    t = AttentionTracker.from_config({"window_seconds": 60, "max_interrupts_per_window": 3, "min_gap_seconds": 5})
    assert (t.window_seconds, t.max_interrupts, t.min_gap_seconds) == (60, 3, 5)


def test_earliest_interrupt_time_now_when_free():
    assert make().earliest_interrupt_time(7) == 7


def test_earliest_interrupt_time_respects_gap():
    t = make()
    t.record_interrupt(0)
    assert t.earliest_interrupt_time(3) == 10


def test_earliest_interrupt_time_waits_for_budget_to_free():
    t = make(min_gap_seconds=0)
    t.record_interrupt(0)
    t.record_interrupt(40)
    # budget 2/100s: at t=50 both in window; first ages out at exactly 100
    assert t.earliest_interrupt_time(50) == 100
    assert t.can_interrupt(100)[0]


def test_earliest_interrupt_time_none_when_budget_zero():
    assert make(max_interrupts=0).earliest_interrupt_time(0) is None


def test_out_of_order_records_are_handled():
    t = make(min_gap_seconds=0)
    t.record_interrupt(50)
    t.record_interrupt(10)
    assert t.interrupts_in_window(60) == 2
