"""Offline tests for the SAML-D loader and the currency handling it required.

No Kaggle access: selection is exercised on tiny inline frames, downloads on fake responses.
"""

from __future__ import annotations

import zipfile

import pandas as pd
import pytest

from core import metrics
from core.agents.validator import validate_narrative
from core.ingest import saml_loader as saml
from core.schemas import Alert, EvidenceItem, EvidencePack, NarrativeSentence, SARNarrative
from core.utils import active_currency, fmt_amount

GBP = "UK pounds"
COLS = [saml.TIME, saml.DATE, saml.SND, saml.RCV, saml.AMT, saml.PCUR, saml.RCUR,
        saml.SLOC, saml.RLOC, saml.PTYPE, saml.LAB, saml.TYP]


def _row(snd, rcv, amt, lab=0, typ="Normal_Small_Fan_Out", date="2023-01-02", time="10:00:00",
         pcur=GBP, rcur=GBP, ptype="ACH"):
    return [time, date, snd, rcv, amt, pcur, rcur, "UK", "UK", ptype, lab, typ]


def _frame() -> pd.DataFrame:
    rows = [
        _row(1, 2, 900.0, 1, "Structuring", date="2023-01-02"),               # kept laundering
        _row(2, 3, 850.0, 1, "Cycle", date="2023-01-03", time="09:00:00"),     # kept laundering
        _row(4, 5, 700.0, 1, "Smurfing", pcur="Euro", rcur="Euro"),            # other currency
        _row(1, 9, 50.0, date="2023-01-04"),                                   # normal, touches 1
        _row(6, 7, 60.0, date="2023-01-05"),                                   # normal background
        _row(7, 8, 70.0, date="2023-01-06"),                                   # normal background
        _row(6, 6, 80.0),                                                      # self transfer
        _row(7, 6, 0.0),                                                       # zero amount
        _row(8, 6, 90.0, rcur="Euro"),                                         # mismatched currency
    ]
    return pd.DataFrame(rows, columns=COLS)


def _chunks(df: pd.DataFrame, size: int = 4) -> list[pd.DataFrame]:
    return [df.iloc[i:i + size].reset_index(drop=True) for i in range(0, len(df), size)]


def test_scan_positives_filters_currency_and_counts_the_whole_file():
    positives, stats = saml.scan_positives(_chunks(_frame()), GBP)
    assert len(positives) == 2 and set(positives[saml.TYP]) == {"Structuring", "Cycle"}
    assert stats["source_rows"] == 9
    assert stats["laundering_total"] == 3          # includes the euro one that was filtered out
    assert stats["laundering_usable"] == 2
    assert stats["usable_rows"] == 5               # 2 laundering + 3 clean GBP normals


def test_pick_normals_separates_context_from_background_deterministically():
    kwargs = dict(normal_rows=3, budget=10, context_share=0.5, seed=7)
    touch, bg = saml.pick_normals(_chunks(_frame()), {1, 2, 3}, GBP, **kwargs)
    assert list(touch[saml.SND]) == [1]                       # only the row touching a bad account
    assert sorted(bg[saml.SND]) == [6, 7]                     # frac is 1.0 here, so both survive
    again = saml.pick_normals(_chunks(_frame()), {1, 2, 3}, GBP, **kwargs)
    assert touch.equals(again[0]) and bg.equals(again[1])


def test_choose_rows_keeps_positives_first_and_respects_the_budget():
    pos, _ = saml.scan_positives(_chunks(_frame()), GBP)
    touch, bg = saml.pick_normals(_chunks(_frame()), {1, 2, 3}, GBP, normal_rows=3,
                                  budget=10, context_share=0.5, seed=7)
    chosen, kept = saml.choose_rows(pos, touch, bg, max_total=4, context_share=0.5, seed=7)
    assert len(chosen) == 4 and kept == {"laundering_kept": 2, "context_kept": 1,
                                         "background_kept": 1}
    capped, kept = saml.choose_rows(pos, touch, bg, max_total=1, context_share=0.5, seed=7)
    assert len(capped) == 1 and kept["laundering_kept"] == 1   # positives alone exceed the cap


def test_remap_ids_currency_and_labels():
    pos, _ = saml.scan_positives(_chunks(_frame()), GBP)
    touch, bg = saml.pick_normals(_chunks(_frame()), {1, 2, 3}, GBP, normal_rows=3,
                                  budget=10, context_share=0.5, seed=7)
    chosen, _ = saml.choose_rows(pos, touch, bg, max_total=10, context_share=0.5, seed=7)
    sample = saml.remap(chosen, "GBP")
    ids = [a["account_id"] for a in sample.accounts]
    assert ids == [f"ACC_{i:04d}" for i in range(1, len(ids) + 1)]
    assert [t["txn_id"] for t in sample.txns] == [f"T{i:06d}" for i in range(1, 6)]
    assert [t["ts"] for t in sample.txns] == sorted(t["ts"] for t in sample.txns)
    assert {t["currency"] for t in sample.txns} == {"GBP"}
    laundering = [t for t in sample.txns if t["is_laundering"]]
    assert {t["gt_pattern"] for t in laundering} == {"Structuring", "Cycle"}
    assert all(t["gt_pattern"] is None and t["gt_ring_id"] is None
               for t in sample.txns if not t["is_laundering"])
    assert sample.stats["typologies_kept"] == {"Structuring": 1, "Cycle": 1}


def test_load_subset_end_to_end_and_second_load_uses_the_saved_sample(monkeypatch, tmp_path):
    monkeypatch.setattr(saml, "SAML_DIR", tmp_path)
    csv = tmp_path / saml.FILENAME
    _frame().to_csv(csv, index=False)
    first_log: list[str] = []
    first = saml.load_saml_subset(path=csv, persist=False, on_progress=first_log.append)
    assert any("pass 1" in m for m in first_log)
    assert first.stats["laundering_kept"] == 2 and first.stats["laundering_total"] == 3
    second_log: list[str] = []
    second = saml.load_saml_subset(path=csv, persist=False, on_progress=second_log.append)
    assert second_log == ["Reusing the sample saved from the last load"]
    assert [(t["sender_id"], t["amount"], t["gt_pattern"]) for t in first.txns] == \
           [(t["sender_id"], t["amount"], t["gt_pattern"]) for t in second.txns]


def test_extract_member_rejects_an_unexpected_archive(tmp_path):
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr(saml.FILENAME, "a,b\n1,2\n")
    saml._extract_member(good, saml.FILENAME, tmp_path)
    assert (tmp_path / saml.FILENAME).read_text() == "a,b\n1,2\n"

    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("elsewhere.csv", "x")
    with pytest.raises(saml.SamlLoaderError):
        saml._extract_member(bad, saml.FILENAME, tmp_path)

    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip at all")
    with pytest.raises(saml.SamlLoaderError):
        saml._extract_member(broken, saml.FILENAME, tmp_path)
    assert not broken.exists()                      # a damaged download is discarded


@pytest.mark.parametrize("serves_zip", [True, False])
def test_download_handles_a_zipped_or_raw_csv(monkeypatch, tmp_path, serves_zip):
    monkeypatch.setattr(saml, "SAML_DIR", tmp_path)

    def fake_download(slug, filename, dest, **kwargs):
        dest.parent.mkdir(parents=True, exist_ok=True)
        if serves_zip:
            with zipfile.ZipFile(dest, "w") as z:
                z.writestr(filename, "a,b\n1,2\n")
        else:
            dest.write_text("a,b\n1,2\n")
        return dest

    monkeypatch.setattr(saml, "download_dataset_file", fake_download)
    path = saml.download_saml_d()
    assert path.read_text() == "a,b\n1,2\n"
    assert not (tmp_path / (saml.FILENAME + ".zip")).exists()


def test_download_without_token_is_friendly(monkeypatch, tmp_path):
    monkeypatch.setattr(saml, "SAML_DIR", tmp_path)
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    with pytest.raises(saml.SamlLoaderError) as exc:
        saml.download_saml_d()
    assert "KAGGLE_API_TOKEN" in str(exc.value) and "data/saml" in str(exc.value)


def test_persist_prints_the_datasets_currency_and_reports_recall_by_type(seeded, rules):
    """A GBP dataset must print GBP everywhere; restoring the demo set restores USD."""
    from core.detection.runner import run_detection
    from core.ingest.generator import generate

    pos, _ = saml.scan_positives(_chunks(_frame()), GBP)
    touch, bg = saml.pick_normals(_chunks(_frame()), {1, 2, 3}, GBP, normal_rows=3,
                                  budget=10, context_share=0.5, seed=7)
    chosen, _ = saml.choose_rows(pos, touch, bg, max_total=10, context_share=0.5, seed=7)
    sample = saml.remap(chosen, "GBP")
    saml.persist_saml(sample, dataset_id="saml_test")

    assert active_currency() == "GBP"
    assert fmt_amount(1200.5) == "1,200.50 GBP"
    first = next(t for t in sample.txns if t["gt_pattern"] == "Structuring")
    alerts = [Alert(alert_id="AL-0001", pattern="fan_in", accounts=[first["sender_id"]],
                    txn_ids=[first["txn_id"]], total_amount=first["amount"], reason="test")]
    by_type = {r["typology"]: r for r in metrics.recall_by_type("saml_test", alerts)}
    assert by_type["Structuring"]["recall"] == 1.0 and by_type["Cycle"]["recall"] == 0.0
    assert by_type["Structuring"]["laundering_txns"] == 1

    generate(seed=42, persist=True, write_csv=False)          # restore the demo dataset
    run_detection("demo_seed42", rules)
    assert active_currency() == "USD"


def test_validator_checks_the_currency_as_well_as_the_amount():
    pack = EvidencePack(
        case_id="C-001", subjects=[{"account_id": "ACC_0001", "risk_score": 50}],
        patterns=["fan_in"], totals={"total_amount": 1200.0, "n_txns": 1},
        items=[EvidenceItem(id="E1", kind="txn",
                            summary="T000001: ACC_0001 -> ACC_0002, 1,200.00 GBP, 2023-01-02 10:00",
                            data={"txn_id": "T000001", "sender": "ACC_0001",
                                  "receiver": "ACC_0002", "amount": 1200.0,
                                  "date": "2023-01-02"})])

    def narrative(text: str) -> SARNarrative:
        return SARNarrative(summary=[NarrativeSentence(text=text, evidence_ids=["E1"])],
                            subjects=[], activity=[], red_flags=[], conclusion=[])

    assert validate_narrative(narrative("ACC_0001 sent 1,200.00 GBP on 2023-01-02."), pack).passed
    wrong = validate_narrative(narrative("ACC_0001 sent 1,200.00 USD on 2023-01-02."), pack)
    assert not wrong.passed and "currency USD differs" in wrong.issues[0].problem
    # Words that merely follow a number are not mistaken for amounts.
    assert validate_narrative(narrative("ACC_0001 made 5 ACH transfers on 2023-01-02."), pack).passed
