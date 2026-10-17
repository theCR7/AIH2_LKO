"""Case grouping must not let hub accounts merge unrelated activity into a mega-case.

Regression found on real-scale (IBM AML) data: transitive merging through shared hub
accounts produced a single 3,553-account case (1.8 billion USD).
"""

from __future__ import annotations

from core.config import load_rules
from core.schemas import AccountRisk, Alert
from core.scoring.cases import build_cases


def _chain(n_alerts: int) -> tuple[list[Alert], dict[str, AccountRisk]]:
    """n alerts of 5 accounts each; consecutive alerts share one hub account."""
    alerts, risk = [], {}
    for i in range(n_alerts):
        accts = [f"ACC_{i * 4 + j + 1:04d}" for j in range(5)]   # last account shared with next
        alerts.append(Alert(alert_id=f"AL-{i + 1:04d}", pattern="fan_out", accounts=accts,
                            txn_ids=[f"T{i + 1:06d}"], total_amount=1000.0 * (i + 1),
                            reason="test"))
        for a in accts:
            risk[a] = AccountRisk(account_id=a, score=40.0 + i, band="medium",
                                  explanation=["+32 member of fan-out layering"])
    return alerts, risk


def test_oversized_component_is_split_one_case_per_alert():
    rules = load_rules().model_copy(deep=True)
    rules.cases.max_case_accounts = 20
    alerts, risk = _chain(12)               # one linked group of 49 accounts > 20
    cases, case_alerts = build_cases(alerts, risk, rules)
    assert len(cases) == 12
    assert all(len(c.accounts) == 5 for c in cases)
    assert sorted(a for v in case_alerts.values() for a in v) == sorted(
        al.alert_id for al in alerts)


def test_normal_sized_component_stays_one_case():
    rules = load_rules().model_copy(deep=True)
    rules.cases.max_case_accounts = 100
    alerts, risk = _chain(12)               # 49 accounts <= 100 -> merged as before
    cases, _ = build_cases(alerts, risk, rules)
    assert len(cases) == 1 and len(cases[0].accounts) == 49


def test_split_is_deterministic():
    rules = load_rules().model_copy(deep=True)
    rules.cases.max_case_accounts = 20
    alerts, risk = _chain(12)
    first = [(c.case_id, tuple(c.accounts), c.score) for c in build_cases(alerts, risk, rules)[0]]
    second = [(c.case_id, tuple(c.accounts), c.score) for c in build_cases(alerts, risk, rules)[0]]
    assert first == second
