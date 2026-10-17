"""Resumable Kaggle file download over the REST API (shared by the dataset loaders).

Authenticates with the ``KAGGLE_API_TOKEN`` bearer token (``.env``), so no extra client
library or username/key pair is needed. A stalled or truncated transfer keeps its
``.part`` file and resumes with an HTTP ``Range`` request; the final length is checked
against ``Content-Length``. Error messages are safe to show: they never contain the token.

No streamlit here (CLAUDE.md hard rule #1).
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

DEFAULT_BLOCK = 1 << 20
DEFAULT_TIMEOUT = 60       # seconds per socket read; a stall triggers a resume
DEFAULT_ATTEMPTS = 8       # resumable attempts before asking the analyst to retry


class KaggleDownloadError(Exception):
    """A download problem the analyst can act on (token, HTTP error, network)."""


def download_dataset_file(slug: str, filename: str, dest: Path, *,
                          on_progress: Callable[[int], None] | None = None,
                          force: bool = False, block: int = DEFAULT_BLOCK,
                          timeout: int = DEFAULT_TIMEOUT, attempts: int = DEFAULT_ATTEMPTS,
                          manual_hint: str = "", retry_hint: str = "") -> Path:
    """Download one file of a Kaggle dataset to ``dest`` (skipped if it already exists).

    Args:
        slug: ``owner/dataset``.
        filename: the file inside the dataset (Kaggle may serve it zipped).
        dest: where the bytes are written (a ``.part`` file is used while downloading).
        on_progress: called with the running byte count.
        force: discard any cached file / partial download first.
        manual_hint: appended to the "no token" message (how to supply the file by hand).
        retry_hint: appended when attempts run out, e.g. "click Load again to resume".
    """
    if dest.exists() and not force:
        return dest

    token = os.getenv("KAGGLE_API_TOKEN", "").strip()
    if not token:
        raise KaggleDownloadError("No Kaggle token configured. Add KAGGLE_API_TOKEN to .env"
                                  + (f", or {manual_hint}" if manual_hint else "."))

    url = f"https://www.kaggle.com/api/v1/datasets/download/{slug}/{filename}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(".part")
    if force:
        partial.unlink(missing_ok=True)

    last_error = "the connection stalled"
    for _attempt in range(attempts):
        have = partial.stat().st_size if partial.exists() else 0
        headers = {"Authorization": f"Bearer {token}"}
        if have:
            headers["Range"] = f"bytes={have}-"   # resume where the last attempt stopped
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                        timeout=timeout) as resp:
                resumed = have > 0 and resp.status == 206
                if not resumed:
                    have = 0
                expected = have + int(resp.headers.get("Content-Length") or 0)
                with open(partial, "ab" if resumed else "wb") as out:
                    total = have
                    while chunk := resp.read(block):
                        out.write(chunk)
                        total += len(chunk)
                        if on_progress:
                            on_progress(total)
            if expected and partial.stat().st_size != expected:
                last_error = "the download ended early"
                continue                        # truncated: resume from what we have
            partial.replace(dest)
            return dest
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and have:        # range past EOF: the file is already complete
                partial.replace(dest)
                return dest
            partial.unlink(missing_ok=True)
            if exc.code in (401, 403):
                raise KaggleDownloadError(
                    f"Kaggle rejected the token (HTTP {exc.code}). "
                    "Check KAGGLE_API_TOKEN in .env.") from None
            raise KaggleDownloadError(
                f"Kaggle returned HTTP {exc.code} for the dataset file.") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"{type(exc).__name__}"   # keep the partial file and resume

    raise KaggleDownloadError(f"The Kaggle download did not finish ({last_error}). Your "
                              "progress is kept" + (f": {retry_hint}" if retry_hint else "."))
