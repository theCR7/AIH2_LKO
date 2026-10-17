"""SAR drafting orchestrator (Phase 1+) — plain-Python state machine.

Later phase: Evidence Builder -> Typology -> Narrative <-> Validator (retry <= 2)
-> persisted ``SarDraft`` + ``ConfidenceSignals`` in ``decision_log``.
Phase 0 placeholder only.
"""

from __future__ import annotations
