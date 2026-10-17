"""Small UI helpers shared across pages: graceful error handling (ITERATIONS P9).

Keeps the app from ever showing a raw traceback. Wrap any risky block (DB read,
generation, detection, drafting) in :func:`friendly_errors` so failures surface as
a calm ``st.error`` with a short, human message instead of crashing the page.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

logger = logging.getLogger("ringsight.ui")


@contextmanager
def friendly_errors(doing: str, *, stop: bool = False) -> Iterator[None]:
    """Run a block, turning any exception into a friendly ``st.error``.

    Args:
        doing: present-tense description, e.g. ``"loading cases"`` — shown to the
            analyst as "Something went wrong while loading cases."
        stop: if True, halt the page after reporting (for errors that make the
            rest of the page meaningless, e.g. a failed initial data load).
    """
    try:
        yield
    except Exception as exc:
        logger.exception("UI error while %s", doing)
        st.error(f"⚠️ Something went wrong while {doing}. "
                 f"The app kept running — you can retry or pick another case.\n\n"
                 f"Details: {type(exc).__name__}: {exc}")
        if stop:
            st.stop()
