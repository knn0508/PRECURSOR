"""Robust HTTP range-reading file object for Earthdata-protected HDF5/netCDF.

Why: on unstable links, fsspec/aiohttp aborts on the first dropped connection.
This reader resolves the Earthdata redirect chain once (requests + ~/_netrc,
which keeps the URS cookies), reads fixed-size blocks with HTTP Range, caches
them, and retries with backoff. h5py / h5netcdf can open it like a local file.
"""
from __future__ import annotations

import io
import threading
import time
from collections import OrderedDict

import requests

_local = threading.local()


def session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()           # trust_env=True -> ~/_netrc for urs.earthdata.nasa.gov
        s.headers["User-Agent"] = "precursor-ai/0.1 (research)"
        _local.s = s
    return s


class RangeFile(io.RawIOBase):
    def __init__(self, url: str, block: int = 64 * 2**10, max_blocks: int = 2048, retries: int = 8, timeout: int = 90):
        self.url, self.block, self.max_blocks, self.retries, self.timeout = url, block, max_blocks, retries, timeout
        self.cache: OrderedDict[int, bytes] = OrderedDict()
        self.pos = 0
        self.final_url = None
        self.size = None
        self.bytes_fetched = 0
        self._resolve()

    # --- HTTP
    def _get(self, start: int, end: int) -> bytes:
        last = None
        for a in range(self.retries):
            try:
                target = self.final_url or self.url
                r = session().get(target, headers={"Range": f"bytes={start}-{end}"}, timeout=self.timeout,
                                  allow_redirects=True)
                if r.status_code in (401, 403) and self.final_url:   # signed URL expired -> re-resolve
                    self.final_url = None
                    continue
                if r.status_code not in (200, 206):
                    raise IOError(f"HTTP {r.status_code} for {self.url}")
                if self.final_url is None and r.history:
                    self.final_url = r.url
                cr = r.headers.get("Content-Range")
                if cr and self.size is None:
                    self.size = int(cr.split("/")[-1])
                data = r.content
                if r.status_code == 200:                               # server ignored Range
                    data = data[start:end + 1]
                if len(data) != end - start + 1 and (self.size is None or end < self.size):
                    raise IOError(f"short read {len(data)} of {end - start + 1}")
                self.bytes_fetched += len(data)
                return data
            except Exception as e:  # network drop, DNS hiccup, short read
                last = e
                time.sleep(min(2 ** a, 30))
        raise IOError(f"failed after {self.retries} retries: {last!r}")

    def _resolve(self):
        self._get(0, 0)
        if self.size is None:
            raise IOError("server did not report file size")

    def _block(self, i: int) -> bytes:
        b = self.cache.get(i)
        if b is not None:
            self.cache.move_to_end(i)
            return b
        start = i * self.block
        end = min(start + self.block, self.size) - 1
        b = self._get(start, end)
        self.cache[i] = b
        if len(self.cache) > self.max_blocks:
            self.cache.popitem(last=False)
        return b

    # --- file API
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=io.SEEK_SET):
        self.pos = off if whence == io.SEEK_SET else self.pos + off if whence == io.SEEK_CUR else self.size + off
        return self.pos

    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        if n <= 0:
            return 0
        out, got = memoryview(buf), 0
        while got < n:
            i, o = divmod(self.pos + got, self.block)
            b = self._block(i)
            k = min(len(b) - o, n - got)
            out[got:got + k] = b[o:o + k]
            got += k
        self.pos += n
        return n


class RangeFS:
    """Minimal fs-like shim so code written for `fs.open(url, ...)` keeps working."""

    def open(self, url, *a, **k):
        return io.BufferedReader(RangeFile(url), buffer_size=2**16)
