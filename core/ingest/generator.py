"""Seeded synthetic transaction generator (PRD F1.1).

Produces realistic background noise (salaries, merchant payments, P2P) plus
planted laundering patterns carrying ground-truth labels, so detection quality
can be measured. Everything is deterministic for a given seed: accounts are
created in a fixed order and transactions are sorted before transaction IDs are
assigned (CLAUDE.md hard rule #11), keeping demo IDs and the LLM cache stable.

Planted patterns are tuned to be detectable by the default ``config/rules.yaml``.
A few *unlabelled* decoys are added so precision is realistically below 1.0.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

from core.config import SAMPLES_DIR
from core.db import init_db, session_scope
from core.models import Account, Identifier, Transaction

# Fixed simulation window start (timezone-naive UTC). Stable across runs.
BASE_DATE = datetime(2026, 9, 1, 9, 0, 0)


@dataclass
class PlantedCounts:
    """How many of each pattern to plant (PRD F1.1 defaults)."""

    cycles: int = 3
    fan_in: int = 2
    fan_out: int = 1
    shared_id: int = 1
    passthrough: int = 1


@dataclass
class GenerationResult:
    """Summary of a generation run."""

    dataset_id: str
    n_accounts: int
    n_txns: int
    n_identifiers: int
    rings: dict[str, list[str]]  # gt_ring_id -> account_ids
    csv_path: str | None = None
    txns: list[dict] = field(default_factory=list)


# --- Account construction ----------------------------------------------------


def _build_accounts(fake: Faker, n_accounts: int) -> list[dict]:
    """Create ``n_accounts`` account specs with deterministic IDs and types.

    A handful are ``payroll`` (legitimate fan-out) and ``merchant`` (legitimate
    fan-in); the rest are ``individual``/``business``. Types drive the
    ``exclude_account_types`` logic in the detectors.
    """
    banks = ["FirstNational", "MetroBank", "Union Savings", "PacificTrust", "EuroCredit"]
    countries = ["US", "GB", "DE", "SG", "AE"]
    n_payroll = max(3, n_accounts // 120)
    n_merchant = max(10, n_accounts // 30)
    n_business = max(15, n_accounts // 12)

    accounts: list[dict] = []
    for i in range(1, n_accounts + 1):
        if i <= n_payroll:
            acct_type = "payroll"
        elif i <= n_payroll + n_merchant:
            acct_type = "merchant"
        elif i <= n_payroll + n_merchant + n_business:
            acct_type = "business"
        else:
            acct_type = "individual"
        accounts.append(
            {
                "account_id": f"ACC_{i:04d}",
                "name": fake.company() if acct_type in ("business", "merchant") else fake.name(),
                "bank": banks[i % len(banks)],
                "country": countries[i % len(countries)],
                "account_type": acct_type,
                "created_at": BASE_DATE - timedelta(days=365 + (i % 400)),
            }
        )
    return accounts


def _by_type(accounts: list[dict], acct_type: str) -> list[str]:
    return [a["account_id"] for a in accounts if a["account_type"] == acct_type]


# --- Transaction helpers -----------------------------------------------------


def _txn(sender: str, receiver: str, amount: float, ts: datetime, *,
         channel: str = "transfer", ip: str | None = None, device: str | None = None,
         is_laundering: int | None = None, gt_pattern: str | None = None,
         gt_ring_id: str | None = None) -> dict:
    """Build a single transaction record (without a txn_id — assigned later)."""
    return {
        "sender_id": sender,
        "receiver_id": receiver,
        "amount": round(amount, 2),
        "ts": ts,
        "channel": channel,
        "ip": ip,
        "device_id": device,
        "is_laundering": is_laundering,
        "gt_pattern": gt_pattern,
        "gt_ring_id": gt_ring_id,
    }


# --- Background noise --------------------------------------------------------


def _gen_background(rng: random.Random, accounts: list[dict], n_txns: int,
                    days: int) -> list[dict]:
    """Generate legitimate background traffic: salaries, merchant payments, P2P.

    Payroll accounts fan-out salaries and merchants fan-in payments *by design*
    — these exercise the ``exclude_account_types`` logic and must not be flagged.
    """
    payroll = _by_type(accounts, "payroll")
    merchants = _by_type(accounts, "merchant")
    individuals = _by_type(accounts, "individual")
    business = _by_type(accounts, "business")
    non_special = individuals + business
    window_minutes = days * 24 * 60
    txns: list[dict] = []

    def rand_ts() -> datetime:
        return BASE_DATE + timedelta(minutes=rng.randint(0, window_minutes))

    # Salaries: each payroll account pays many individuals (legitimate fan-out).
    for pay in payroll:
        for emp in rng.sample(individuals, k=min(40, len(individuals))):
            txns.append(_txn(pay, emp, rng.uniform(2500, 6500), rand_ts(), channel="payroll"))

    # Merchant payments: individuals pay merchants (legitimate fan-in).
    n_merchant_pay = int(n_txns * 0.35)
    for _ in range(n_merchant_pay):
        txns.append(
            _txn(rng.choice(non_special), rng.choice(merchants),
                 rng.uniform(5, 400), rand_ts(), channel="card")
        )

    # P2P noise: small transfers between individuals/business.
    n_p2p = max(0, n_txns - len(txns))
    for _ in range(n_p2p):
        s, r = rng.sample(non_special, k=2)
        txns.append(_txn(s, r, rng.uniform(20, 900), rand_ts(), channel="p2p"))

    return txns


# --- Planted laundering patterns --------------------------------------------


def _plant_cycle(pool: list[str], ring_id: str, length: int,
                 start: datetime, start_amount: float) -> list[dict]:
    """Plant one circular flow: A->B->...->A, each hop within days, >=80% retained."""
    members = pool[:length]
    txns: list[dict] = []
    amount = start_amount
    ts = start
    for i in range(length):
        sender = members[i]
        receiver = members[(i + 1) % length]
        txns.append(
            _txn(sender, receiver, amount, ts, is_laundering=1,
                 gt_pattern="cycle", gt_ring_id=ring_id)
        )
        amount *= 0.93  # retains 93% per hop (>= 0.80 threshold)
        ts += timedelta(hours=18)  # whole loop well within 7-day window
    return txns


def _plant_fan_in(senders: list[str], receiver: str, ring_id: str,
                  rng: random.Random, start: datetime) -> list[dict]:
    """Plant smurfing: >=5 distinct senders -> 1 receiver, each < 10k, within 48h."""
    txns: list[dict] = []
    ts = start
    for s in senders:
        txns.append(
            _txn(s, receiver, rng.uniform(4000, 9500), ts, is_laundering=1,
                 gt_pattern="fan_in", gt_ring_id=ring_id)
        )
        ts += timedelta(hours=6)  # all within 48h
    return txns


def _plant_fan_out(sender: str, receivers: list[str], ring_id: str,
                   rng: random.Random, start: datetime) -> list[dict]:
    """Plant layering: 1 sender -> >=5 receivers within 48h, total >= 50k."""
    txns: list[dict] = []
    ts = start
    for r in receivers:
        txns.append(
            _txn(sender, r, rng.uniform(9000, 12000), ts, is_laundering=1,
                 gt_pattern="fan_out", gt_ring_id=ring_id)
        )
        ts += timedelta(hours=5)
    return txns


def _plant_passthrough(inflow_src: str, hub: str, outflow_dst: str, ring_id: str,
                       start: datetime, amount: float) -> list[dict]:
    """Plant rapid pass-through: inflow then >=90% outflow within 24h."""
    return [
        _txn(inflow_src, hub, amount, start, is_laundering=1,
             gt_pattern="passthrough", gt_ring_id=ring_id),
        _txn(hub, outflow_dst, amount * 0.95, start + timedelta(hours=8),
             is_laundering=1, gt_pattern="passthrough", gt_ring_id=ring_id),
    ]


def _plant_patterns(rng: random.Random, accounts: list[dict], planted: PlantedCounts,
                    ) -> tuple[list[dict], dict[str, list[str]], list[dict]]:
    """Plant all labelled patterns and shared-identifier records.

    Returns ``(txns, rings, identifiers)`` where ``rings`` maps ring id to its
    member accounts (used by metrics for ground-truth matching).
    """
    # Draw a dedicated pool of individual/business accounts for planted rings so
    # they never collide with excluded merchant/payroll accounts.
    candidates = _by_type(accounts, "individual") + _by_type(accounts, "business")
    pool = list(candidates)
    rng.shuffle(pool)
    cursor = 0

    def take(n: int) -> list[str]:
        nonlocal cursor
        chunk = pool[cursor : cursor + n]
        cursor += n
        return chunk

    txns: list[dict] = []
    rings: dict[str, list[str]] = {}
    identifiers: list[dict] = []
    ring_seq = 1

    def next_ring() -> str:
        nonlocal ring_seq
        rid = f"R-{ring_seq:02d}"
        ring_seq += 1
        return rid

    # Cycles (varying lengths 4,3,5,... cycling through 3..6).
    for c in range(planted.cycles):
        length = (c % 4) + 3  # 3..6
        members = take(length)
        rid = next_ring()
        rings[rid] = members
        txns += _plant_cycle(members, rid, length,
                             BASE_DATE + timedelta(days=2 + c * 3), 50000 + c * 10000)

    # Fan-in smurfing.
    for _ in range(planted.fan_in):
        receiver = take(1)[0]
        senders = take(6)
        rid = next_ring()
        rings[rid] = [receiver, *senders]
        txns += _plant_fan_in(senders, receiver, rid, rng,
                              BASE_DATE + timedelta(days=10))

    # Fan-out layering.
    for _ in range(planted.fan_out):
        sender = take(1)[0]
        receivers = take(6)
        rid = next_ring()
        rings[rid] = [sender, *receivers]
        txns += _plant_fan_out(sender, receivers, rid, rng,
                              BASE_DATE + timedelta(days=14))

    # Shared-identifier cluster.
    for _ in range(planted.shared_id):
        members = take(4)
        rid = next_ring()
        rings[rid] = members
        device = "DEV_009"
        for m in members:
            identifiers.append({"account_id": m, "id_type": "device", "value": device})
        # A couple of transfers so the cluster appears in the money graph too.
        txns.append(_txn(members[0], members[1], 7200, BASE_DATE + timedelta(days=18),
                         device=device, is_laundering=1, gt_pattern="shared_identifier",
                         gt_ring_id=rid))
        txns.append(_txn(members[2], members[3], 6100, BASE_DATE + timedelta(days=18, hours=3),
                         device=device, is_laundering=1, gt_pattern="shared_identifier",
                         gt_ring_id=rid))

    # Rapid pass-through.
    for _ in range(planted.passthrough):
        src, hub, dst = take(3)
        rid = next_ring()
        rings[rid] = [src, hub, dst]
        txns += _plant_passthrough(src, hub, dst, rid,
                                   BASE_DATE + timedelta(days=20), 48200)

    # --- Unlabelled decoys (create realistic false positives) ---------------
    # Decoy 1: 3 individuals sharing an IP (e.g. roommates) -> shared_identifier FP.
    decoy_ip_accts = take(3)
    for m in decoy_ip_accts:
        identifiers.append({"account_id": m, "id_type": "ip", "value": "192.0.2.50"})

    # Decoy 2: 5 individuals send to one individual within 48h (group gift) -> fan_in FP.
    gift_receiver = take(1)[0]
    gift_senders = take(5)
    ts = BASE_DATE + timedelta(days=24)
    for s in gift_senders:
        txns.append(_txn(s, gift_receiver, rng.uniform(1500, 4000), ts, channel="p2p"))
        ts += timedelta(hours=7)

    return txns, rings, identifiers


# --- Orchestration -----------------------------------------------------------


def _assign_txn_ids(txns: list[dict]) -> list[dict]:
    """Sort transactions deterministically and assign stable ``T000001`` ids."""
    txns_sorted = sorted(
        txns,
        key=lambda t: (t["ts"], t["sender_id"], t["receiver_id"], t["amount"]),
    )
    for i, t in enumerate(txns_sorted, start=1):
        t["txn_id"] = f"T{i:06d}"
    return txns_sorted


def _persist(accounts: list[dict], txns: list[dict], identifiers: list[dict],
             dataset_id: str) -> None:
    """Write accounts, transactions and identifiers to the database."""
    init_db()
    with session_scope() as session:
        # Clear any prior rows for this dataset for a clean, repeatable demo.
        session.query(Transaction).filter(Transaction.dataset_id == dataset_id).delete()
        session.query(Identifier).delete()
        session.query(Account).delete()
        session.flush()
        session.bulk_insert_mappings(Account, accounts)
        session.bulk_insert_mappings(
            Transaction,
            [
                {
                    "txn_id": t["txn_id"], "sender_id": t["sender_id"],
                    "receiver_id": t["receiver_id"], "amount": t["amount"],
                    "currency": "USD", "ts": t["ts"], "channel": t["channel"],
                    "ip": t["ip"], "device_id": t["device_id"],
                    "is_laundering": t["is_laundering"], "gt_pattern": t["gt_pattern"],
                    "gt_ring_id": t["gt_ring_id"], "dataset_id": dataset_id,
                }
                for t in txns
            ],
        )
        session.bulk_insert_mappings(Identifier, identifiers)


def _write_csv(txns: list[dict], dataset_id: str, path: Path) -> None:
    """Export the transaction table to a CSV sample."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "txn_id": t["txn_id"], "sender_id": t["sender_id"],
            "receiver_id": t["receiver_id"], "amount": t["amount"], "currency": "USD",
            "ts": t["ts"].strftime("%Y-%m-%d %H:%M:%S"), "channel": t["channel"],
            "ip": t["ip"] or "", "device_id": t["device_id"] or "",
            "is_laundering": "" if t["is_laundering"] is None else t["is_laundering"],
            "gt_pattern": t["gt_pattern"] or "", "gt_ring_id": t["gt_ring_id"] or "",
            "dataset_id": dataset_id,
        }
        for t in txns
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def generate(n_accounts: int = 500, n_txns: int = 5000, days: int = 30, seed: int = 42,
             planted: PlantedCounts | None = None, dataset_id: str | None = None,
             persist: bool = True, write_csv: bool = True) -> GenerationResult:
    """Generate a synthetic dataset with planted, labelled laundering patterns.

    Args:
        n_accounts: approximate number of accounts.
        n_txns: approximate number of background transactions (planted ones add a few more).
        days: length of the simulation window.
        seed: RNG seed — same seed yields identical data and IDs.
        planted: how many of each pattern to plant (defaults to PRD F1.1).
        dataset_id: logical dataset name; defaults to ``demo_seed{seed}``.
        persist: write accounts/txns/identifiers to the DB.
        write_csv: export transactions to ``data/samples/<dataset_id>.csv``.
    """
    planted = planted or PlantedCounts()
    dataset_id = dataset_id or f"demo_seed{seed}"
    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)

    accounts = _build_accounts(fake, n_accounts)
    planted_txns, rings, identifiers = _plant_patterns(rng, accounts, planted)
    background_txns = _gen_background(rng, accounts, n_txns, days)

    all_txns = _assign_txn_ids(planted_txns + background_txns)

    csv_path: str | None = None
    if write_csv:
        out = SAMPLES_DIR / f"{dataset_id}.csv"
        _write_csv(all_txns, dataset_id, out)
        csv_path = str(out)

    if persist:
        _persist(accounts, all_txns, identifiers, dataset_id)

    return GenerationResult(
        dataset_id=dataset_id,
        n_accounts=len(accounts),
        n_txns=len(all_txns),
        n_identifiers=len(identifiers),
        rings=rings,
        csv_path=csv_path,
        txns=all_txns,
    )


if __name__ == "__main__":
    res = generate()
    print(f"Generated {res.n_txns} txns / {res.n_accounts} accounts "
          f"for dataset '{res.dataset_id}'.")
    print(f"Planted rings: {list(res.rings)}")
    if res.csv_path:
        print(f"CSV written to {res.csv_path}")
