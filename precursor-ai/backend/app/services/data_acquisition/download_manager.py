"""Resumable, verified, atomic file downloads. Byte transfer only; no interpretation of content."""
from __future__ import annotations

import hashlib
import logging
import os
import random
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

import requests

from app.services.data_acquisition.types import AuthenticationError, DownloadError, DownloadResult

log = logging.getLogger(__name__)

CHUNK = 1 << 20
PROGRESS_BYTES = 1 << 20
PROGRESS_SECONDS = 0.5
_ALGOS = {"md5": "md5", "sha256": "sha256", "sha-256": "sha256", "sha1": "sha1", "sha-1": "sha1"}


def hash_file(path: Path, *algorithms: str) -> dict[str, str]:
    """Streaming hex digests of `path` for the given hashlib names."""
    hs = {a: hashlib.new(a) for a in algorithms}
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            for h in hs.values():
                h.update(chunk)
    return {a: h.hexdigest() for a, h in hs.items()}


def normalize_algorithm(name: str | None) -> str | None:
    if not name:
        return None
    try:
        return _ALGOS[name.strip().lower()]
    except KeyError:
        raise DownloadError(f"unsupported checksum algorithm: {name}", retryable=False) from None


class _Truncated(Exception):
    """Stream ended early; the .part is kept so the next attempt can resume."""


class DownloadManager:
    def __init__(self, settings, *, sleep=time.sleep, session_factory: Callable[[], requests.Session] | None = None):
        self.settings = settings
        self._sleep = sleep
        self._session_factory = session_factory

    # ---- public ---------------------------------------------------------------
    def download(
        self,
        url: str,
        dest_path: Path,
        *,
        expected_size: int | None = None,
        checksum: str | None = None,
        checksum_algorithm: str | None = None,
        progress: Callable[[int, int | None], None] | None = None,
        session=None,
    ) -> DownloadResult:
        dest = Path(dest_path)
        algo = normalize_algorithm(checksum_algorithm) if checksum else None
        if checksum and not algo:
            raise DownloadError("checksum given without checksum_algorithm", retryable=False)
        host = urlsplit(url).hostname
        cap = self.settings.max_file_size_bytes
        if expected_size is not None and expected_size > cap:
            raise DownloadError(f"expected size {expected_size} exceeds limit {cap}", retryable=False)

        if dest.exists():
            return self._existing(dest, expected_size, checksum, algo)

        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        if expected_size is not None:
            need = int(expected_size * 1.05) - (part.stat().st_size if part.exists() else 0)
            if shutil.disk_usage(dest.parent).free < need:
                raise DownloadError("not enough free disk space", retryable=False)

        session = session or (self._session_factory() if self._session_factory else requests.Session())
        retries = self.settings.download_retries
        log.info("download start host=%s dest=%s", host, dest.name)
        last: Exception | None = None
        for attempt in range(retries + 1):
            if attempt:
                delay = 2 ** (attempt - 1) + random.uniform(0, 0.25)
                log.warning("download retry host=%s attempt=%d delay=%.1fs reason=%s", host, attempt, delay, last)
                self._sleep(delay)
            try:
                resumed = self._attempt(session, url, part, expected_size, checksum, algo, progress)
                break
            except (requests.Timeout, requests.ConnectionError, requests.exceptions.ChunkedEncodingError, _Truncated) as e:
                last = e
            except DownloadError as e:
                if not e.retryable:
                    raise
                last = e
        else:
            raise DownloadError(f"download failed after {retries + 1} attempts: {last}", retryable=True) from last

        os.replace(part, dest)
        sha = hash_file(dest, "sha256")["sha256"]
        size = dest.stat().st_size
        log.info("download finished host=%s dest=%s size=%d resumed=%s", host, dest.name, size, resumed)
        return DownloadResult(path=dest, size_bytes=size, sha256=sha, resumed=resumed)

    # ---- internals ------------------------------------------------------------
    def _existing(self, dest: Path, expected_size, checksum, algo) -> DownloadResult:
        size = dest.stat().st_size
        if checksum:
            digests = hash_file(dest, "sha256", algo)
            same = digests[algo].lower() == checksum.strip().lower()
        elif expected_size is not None:
            same = size == expected_size
        else:
            same = False  # nothing to verify against: never assume
        if not same:
            raise DownloadError(f"refusing to overwrite existing file {dest.name}", retryable=False)
        log.info("download skipped (already present) dest=%s", dest.name)
        return DownloadResult(path=dest, size_bytes=size, sha256=hash_file(dest, "sha256")["sha256"], resumed=False)

    def _attempt(self, session, url, part: Path, expected_size, checksum, algo, progress) -> bool:
        offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        resp = session.get(url, headers=headers, stream=True, timeout=self.settings.request_timeout_s)
        try:
            code = resp.status_code
            if code in (401, 403):
                raise AuthenticationError(f"authentication rejected (HTTP {code}); check Earthdata credentials")
            if code in (404, 410):
                raise DownloadError(f"resource not available (HTTP {code})", retryable=False)
            if code == 416:  # range not satisfiable: part is complete or corrupt
                self._verify(part, expected_size, checksum, algo)
                return True
            if code == 429 or code >= 500:
                raise DownloadError(f"server error HTTP {code}")
            if code not in (200, 206):
                raise DownloadError(f"unexpected HTTP {code}", retryable=False)

            if code == 206:
                m = re.match(r"bytes (\d+)-(\d+)/(\d+|\*)", resp.headers.get("Content-Range", ""))
                if not m or int(m.group(1)) != offset:
                    part.unlink(missing_ok=True)
                    raise DownloadError("server returned an inconsistent Content-Range; restarting")
                total = int(m.group(3)) if m.group(3) != "*" else expected_size
            else:
                offset = 0  # Range ignored (or fresh download): start over
                cl = resp.headers.get("Content-Length")
                total = int(cl) if cl and cl.isdigit() else expected_size
            if expected_size is not None and total is not None and total != expected_size:
                raise DownloadError(f"size mismatch: server says {total}, expected {expected_size}", retryable=False)
            cap = self.settings.max_file_size_bytes
            if total is not None and total > cap:
                raise DownloadError(f"file size {total} exceeds limit {cap}", retryable=False)

            done = offset
            last_report, last_t = done, time.monotonic()
            with part.open("ab" if offset else "wb") as f:
                for chunk in resp.iter_content(CHUNK):
                    done += len(chunk)
                    if done > cap:
                        f.close()
                        part.unlink(missing_ok=True)
                        raise DownloadError(f"download exceeded size limit {cap}", retryable=False)
                    f.write(chunk)
                    now = time.monotonic()
                    if progress and (done - last_report >= PROGRESS_BYTES or now - last_t >= PROGRESS_SECONDS):
                        progress(done, total)
                        last_report, last_t = done, now
            if progress:
                progress(done, total)
            if total is not None and done < total:
                raise _Truncated(f"stream ended at {done}/{total} bytes")
            self._verify(part, expected_size or total, checksum, algo)
            return code == 206
        finally:
            resp.close()

    def _verify(self, part: Path, size, checksum, algo) -> None:
        actual = part.stat().st_size
        if size is not None and actual != size:
            part.unlink(missing_ok=True)
            raise DownloadError(f"size mismatch: got {actual}, expected {size}")
        if checksum and hash_file(part, algo)[algo].lower() != checksum.strip().lower():
            part.unlink(missing_ok=True)
            raise DownloadError(f"{algo} checksum mismatch")
