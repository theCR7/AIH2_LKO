"""A pattern must count once per account, however many alerts repeat it.

Regression found on real (IBM AML) data: an account in four pass-through alerts stacked
4 x 25 points, hit the cap, and the top ten cases all scored 100.
"""

from __future__ import annotations

from datetime import datetime

from core.config import load_rules
from core.detection.graph_builder import TxnRecord, build_graph
from core.schemas import Alert
from core.scoring.risk import score_accounts

T0 = datetime(2026, 9, 1, 9, 0)


def _bundle_and_alerts(n_repeats: int):
    accounts = ["ACC_0001", "ACC_0002", "ACC_0003"]
    txns = [TxnRecord(txn_id="T000001", sender_id="ACC_0002", receiver_id="ACC_0001",
                      amount=6000.0, ts=T0),
            TxnRecord(txn_id="T000002", sender_id="ACC_0001", receiver_id="ACC_0003",
                      amount=5900.0, ts=T0)]
    bundle = build_graph(txns, {a: "individual" for a in accounts})
    alerts = [Alert(alert_id=f"AL-{i + 1:04d}", pattern="passthrough", accounts=accounts,
                    txn_ids=["T000001", "T000002"], total_amount=6000.0, reason="test")
              for i in range(n_repeats)]
    return bundle, alerts


def test_repeated_alerts_of_one_pattern_do_not_stack():
    rules = load_rules()
    weight = rules.scoring.weights["passthrough"]
    one = score_accounts(*_bundle_and_alerts(1), rules)["ACC_0001"]
    four = score_accounts(*_bundle_and_alerts(4), rules)["ACC_0001"]
    assert four.score == one.score                 # the weight is counted once
    assert one.score <= weight + 2 * max(rules.scoring.centrality.pagerank_weight,
                                         rules.scoring.centrality.betweenness_weight)
    assert any("+3 more" in line for line in four.explanation)   # repeats are noted
    assert not any("more" in line for line in one.explanation)
