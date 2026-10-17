"""Fan-in/out need a ceiling: an account paying thousands is an institution, not a mule.

Regression found on real (IBM AML) data: one account paying 3,411 receivers in 48 h
(1.8 billion USD) became the top-ranked 'layering' case.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from core.config import load_rules
from core.detection.fan_patterns import detect_fan_in, detect_fan_out
from core.detection.graph_builder import TxnRecord, build_graph

T0 = datetime(2026, 9, 1, 9, 0)


def _fan_out(n_receivers: int, amount: float = 20000.0):
    txns = [TxnRecord(txn_id=f"T{i:06d}", sender_id="ACC_0001",
                      receiver_id=f"ACC_{i + 10:04d}", amount=amount,
                      ts=T0 + timedelta(minutes=i))
            for i in range(1, n_receivers + 1)]
    accounts = {t.sender_id: "individual" for t in txns} | \
               {t.receiver_id: "individual" for t in txns}
    return build_graph(txns, accounts)


def _fan_in(n_senders: int, amount: float = 5000.0):
    txns = [TxnRecord(txn_id=f"T{i:06d}", sender_id=f"ACC_{i + 10:04d}",
                      receiver_id="ACC_0001", amount=amount,
                      ts=T0 + timedelta(minutes=i))
            for i in range(1, n_senders + 1)]
    accounts = {t.sender_id: "individual" for t in txns} | \
               {t.receiver_id: "individual" for t in txns}
    return build_graph(txns, accounts)


def test_fan_out_flags_a_plausible_mule_distribution():
    assert len(detect_fan_out(_fan_out(6), load_rules())) == 1


def test_fan_out_ignores_a_mass_payer():
    rules = load_rules()
    assert detect_fan_out(_fan_out(rules.fan_out.max_receivers + 50), rules) == []


def test_fan_in_flags_plausible_structuring():
    assert len(detect_fan_in(_fan_in(6), load_rules())) == 1


def test_fan_in_ignores_an_institutional_payee():
    rules = load_rules()
    assert detect_fan_in(_fan_in(rules.fan_in.max_senders + 50), rules) == []
