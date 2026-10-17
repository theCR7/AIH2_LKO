"""Validator Agent (deterministic) — the grounding differentiator (ARCHITECTURE §6).

For every narrative sentence it checks, against the cited evidence only:
1. ``evidence_ids`` is non-empty and every id exists in the pack.
2. every amount (``48,200.00 USD``) matches an amount in the cited evidence (±1%) and is
   stated in the same currency as that evidence.
3. every account id (``ACC_0018``) is in the cited evidence or the subjects.
4. every date (``2026-09-03``) falls inside the cited evidence dates/ranges.
5. speculation lexicon: reject identity/intent claims the evidence cannot support.

Grounding Score = passed sentences / total * 100. This module is the source of
truth (CLAUDE.md rule #6); the LLM judge (rules.yaml ``use_llm_judge``) is optional
and not required for the MVP.
"""

from __future__ import annotations

import re

from core.config import Rules, load_rules
from core.schemas import EvidenceItem, EvidencePack, SARNarrative, ValidationIssue, ValidationResult

# ISO codes the app can print (the dataset's own currency, see core.utils.active_currency).
_CURRENCY_CODES = ("USD", "GBP", "EUR", "CHF", "CNY", "INR", "AED", "TRY", "MXN", "MAD",
                   "PKR", "NGN", "JPY", "CAD", "AUD", "ILS", "SAR")
_AMOUNT_RE = re.compile(r"(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(" + "|".join(_CURRENCY_CODES) + r")\b")
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
# 4+ digits: datasets with more than 9,999 accounts mint ids like ACC_10042; an
# exact {4} match would silently skip account grounding for them.
_ACCT_RE = re.compile(r"\b(ACC_\d{4,})\b")

_SECTIONS = ["summary", "subjects", "activity", "red_flags", "conclusion"]


def _parse_amount(text: str) -> float:
    return float(text.replace(",", ""))


def _amounts_in(text: str) -> list[tuple[float, str]]:
    """Every ``<amount> <ISO code>`` in the text as ``(value, code)``."""
    return [(_parse_amount(value), code) for value, code in _AMOUNT_RE.findall(text)]


def _allowed_facts(cited: list[EvidenceItem], subjects_accounts: set[str],
                   ) -> tuple[list[float], set[str], list[tuple[str, str]], set[str], set[str]]:
    """Collect allowed amounts, dates, date-ranges, accounts and currencies from evidence."""
    amounts: list[float] = []
    currencies: set[str] = set()
    dates: set[str] = set()
    ranges: list[tuple[str, str]] = []
    accounts: set[str] = set(subjects_accounts)

    for it in cited:
        data = it.data
        for field in ("amount", "total_amount"):
            if isinstance(data.get(field), (int, float)):
                amounts.append(float(data[field]))
        for value, code in _amounts_in(it.summary):
            amounts.append(value)
            currencies.add(code)
        if isinstance(data.get("date"), str):
            dates.add(data["date"])
        if isinstance(data.get("date_range"), str):
            ds = _DATE_RE.findall(data["date_range"])
            if len(ds) == 2:
                ranges.append((ds[0], ds[1]))
            dates.update(ds)
        dates.update(_DATE_RE.findall(it.summary))
        for field in ("sender", "receiver"):
            if isinstance(data.get(field), str):
                accounts.add(data[field])
        if isinstance(data.get("accounts"), list):
            accounts.update(data["accounts"])
        accounts.update(_ACCT_RE.findall(it.summary))
    return amounts, dates, ranges, accounts, currencies


def _date_ok(date: str, dates: set[str], ranges: list[tuple[str, str]]) -> bool:
    if date in dates:
        return True
    return any(lo <= date <= hi for lo, hi in ranges)


def validate_narrative(narrative: SARNarrative, pack: EvidencePack,
                       rules: Rules | None = None) -> ValidationResult:
    """Validate every sentence against the evidence pack and score grounding."""
    rules = rules or load_rules()
    tol = rules.validator.amount_tolerance
    lexicon = [t.lower() for t in rules.validator.speculation_lexicon]
    by_id = {it.id: it for it in pack.items}
    subject_accounts = {s["account_id"] for s in pack.subjects}

    issues: list[ValidationIssue] = []
    total = 0
    passed = 0

    for section in _SECTIONS:
        sentences = getattr(narrative, section)
        for index, sent in enumerate(sentences):
            total += 1
            problems: list[str] = []

            # Rule 1: citations present and valid.
            if not sent.evidence_ids:
                problems.append("sentence has no evidence_ids")
            unknown = [e for e in sent.evidence_ids if e not in by_id]
            if unknown:
                problems.append(f"unknown evidence ids: {', '.join(unknown)}")

            cited = [by_id[e] for e in sent.evidence_ids if e in by_id]
            amounts, dates, ranges, accounts, currencies = _allowed_facts(cited, subject_accounts)

            # Rule 2: amounts match cited evidence (±tol), in the evidence's own currency.
            for amt, code in _amounts_in(sent.text):
                if not any(abs(amt - a) <= tol * max(a, 1.0) for a in amounts):
                    problems.append(f"amount {amt:,.2f} {code} not supported by cited evidence")
                elif currencies and code not in currencies:
                    problems.append(f"currency {code} differs from the cited evidence "
                                    f"({', '.join(sorted(currencies))})")

            # Rule 3: account ids exist in cited evidence or subjects.
            for acct in _ACCT_RE.findall(sent.text):
                if acct not in accounts:
                    problems.append(f"account {acct} not in cited evidence or subjects")

            # Rule 4: dates fall inside cited evidence dates/ranges.
            for date in _DATE_RE.findall(sent.text):
                if not _date_ok(date, dates, ranges):
                    problems.append(f"date {date} outside cited evidence dates")

            # Rule 5: speculation lexicon.
            low = sent.text.lower()
            for term in lexicon:
                if term in low:
                    problems.append(f"speculative/unsupported claim: '{term}'")

            if problems:
                issues.append(ValidationIssue(section=section, index=index,
                                             problem="; ".join(problems)))
            else:
                passed += 1

    grounding = 100.0 if total == 0 else round(passed / total * 100, 1)
    return ValidationResult(grounding_score=grounding, issues=issues,
                            passed=(grounding >= 100.0))
