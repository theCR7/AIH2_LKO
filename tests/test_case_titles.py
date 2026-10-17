"""Case titles must name the account a fan pattern is about, not an arbitrary member.

Regression: every account appears once in a fan-in/fan-out alert, so the old
count-based "hub" fell through to the alphabetically first account. On seed 42 a
fan-in case was titled "involving ACC_0069" (a sender) while the funds were
collected by ACC_0249.
"""

from __future__ import annotations

from core.config import load_rules
from core.schemas import AccountRisk, Alert
from core.scoring.cases import build_cases
from core.scoring.risk import score_accounts


def _risk(accounts: list[str]) -> dict[str, AccountRisk]:
    return {a: AccountRisk(account_id=a, score=50.0, band="medium", explanation=["+30 test"])
            for a in accounts}


def _fan_alert(pattern: str, focus: str, others: list[str], total: float = 1000.0,
               alert_id: str = "AL-0001") -> Alert:
    accounts = sorted([focus, *others])
    return Alert(alert_id=alert_id, pattern=pattern, accounts=accounts,
                 txn_ids=["T000001"], total_amount=total, reason="test", focus=focus)


def test_fan_in_title_names_the_receiver():
    # ACC_0001 sorts first but is only a sender; ACC_0900 is the collecting account.
    alert = _fan_alert("fan_in", focus="ACC_0900", others=[f"ACC_000{i}" for i in range(1, 6)])
    cases, _ = build_cases([alert], _risk(alert.accounts), load_rules())
    assert cases[0].title.endswith("ACC_0900")
    assert "ACC_0001" not in cases[0].title


def test_fan_out_title_names_the_sender():
    alert = _fan_alert("fan_out", focus="ACC_0900", others=[f"ACC_000{i}" for i in range(1, 6)])
    cases, _ = build_cases([alert], _risk(alert.accounts), load_rules())
    assert cases[0].title.endswith("ACC_0900")


def test_title_uses_largest_alert_when_case_has_several():
    small = _fan_alert("fan_in", focus="ACC_0800", others=["ACC_0001", "ACC_0002"],
                       total=500.0, alert_id="AL-0001")
    big = _fan_alert("fan_in", focus="ACC_0900", others=["ACC_0002", "ACC_0003"],
                     total=9000.0, alert_id="AL-0002")
    accounts = sorted({*small.accounts, *big.accounts})
    cases, _ = build_cases([small, big], _risk(accounts), load_rules())
    assert len(cases) == 1
    assert cases[0].title.endswith("ACC_0900")


def test_title_falls_back_when_focus_missing():
    """Alerts without a focus (older data) still get a sensible title."""
    alert = Alert(alert_id="AL-0001", pattern="fan_in",
                  accounts=["ACC_0001", "ACC_0002", "ACC_0003"], txn_ids=["T000001"],
                  total_amount=100.0, reason="test")
    cases, _ = build_cases([alert], _risk(alert.accounts), load_rules())
    assert cases[0].title.startswith("Structuring (fan-in) involving ACC_")


def test_detectors_set_focus_to_the_real_counterparty(seeded, rules):
    """On seed 42 every fan alert's focus is the receiver (fan-in) / sender (fan-out)."""
    bundle, alerts = seeded["bundle"], seeded["alerts"]
    by_id = {t.txn_id: t for t in bundle.txns}
    fan = [a for a in alerts if a.pattern in ("fan_in", "fan_out")]
    assert fan, "seed 42 should contain fan alerts"
    for alert in fan:
        assert alert.focus is not None
        side = "receiver_id" if alert.pattern == "fan_in" else "sender_id"
        assert all(getattr(by_id[t], side) == alert.focus for t in alert.txn_ids)

    risk = score_accounts(bundle, alerts, rules)
    cases, case_alerts = build_cases(alerts, risk, rules)
    alert_by_id = {a.alert_id: a for a in alerts}
    for case in cases:
        if case.patterns and case.patterns[0] in ("fan_in", "fan_out"):
            foci = {alert_by_id[i].focus for i in case_alerts[case.case_id]
                    if alert_by_id[i].pattern == case.patterns[0]}
            assert case.title.rsplit(" ", 1)[-1] in foci
