"""TEST FIXTURE, synthetic, not a NASA acquisition: payloads are random bytes served from 127.0.0.1."""
import hashlib
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from app.services.data_acquisition.download_manager import DownloadManager
from app.services.data_acquisition.types import AuthenticationError, DownloadError

PAYLOAD = os.urandom(3 * 1024 * 1024 + 123)
SHA = hashlib.sha256(PAYLOAD).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        srv = self.server
        srv.requests.append(self.headers.get("Range"))
        if srv.statuses:
            code = srv.statuses.pop(0)
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data, start, code = srv.payload, 0, 200
        rng = self.headers.get("Range")
        if rng and srv.ranges:
            start = int(rng.split("=")[1].rstrip("-"))
            if start >= len(data):
                self.send_response(416)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            code = 206
        self.send_response(code)
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        body = data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if srv.cut_first and not srv.cut_done:
            srv.cut_done = True
            self.wfile.write(body[: len(body) // 2])
            self.wfile.flush()
            self.close_connection = True
            return
        self.wfile.write(body)


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.payload, srv.ranges, srv.statuses, srv.requests = PAYLOAD, True, [], []
    srv.cut_first, srv.cut_done = False, False
    srv.url = f"http://127.0.0.1:{srv.server_port}/f.bin?token=SECRET"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def sleeps():
    return []


def mgr(sleeps, **kw):
    s = dict(request_timeout_s=5, download_retries=3, max_file_size_bytes=10 * 1024**2)
    s.update(kw)
    return DownloadManager(SimpleNamespace(**s), sleep=sleeps.append)


def test_basic_download_atomic(server, sleeps, tmp_path):
    dest = tmp_path / "sub" / "f.bin"
    r = mgr(sleeps).download(server.url, dest, expected_size=len(PAYLOAD), checksum=SHA.upper(), checksum_algorithm="sha256")
    assert dest.read_bytes() == PAYLOAD and r.sha256 == SHA and not r.resumed
    assert not dest.with_name("f.bin.part").exists()


def test_md5_checksum(server, sleeps, tmp_path):
    md5 = hashlib.md5(PAYLOAD).hexdigest()
    assert mgr(sleeps).download(server.url, tmp_path / "f", checksum=md5, checksum_algorithm="MD5").size_bytes == len(PAYLOAD)


def test_resume_with_range(server, sleeps, tmp_path):
    dest = tmp_path / "f.bin"
    dest.with_name("f.bin.part").write_bytes(PAYLOAD[:1000])
    r = mgr(sleeps).download(server.url, dest, checksum=SHA, checksum_algorithm="sha256")
    assert r.resumed and dest.read_bytes() == PAYLOAD
    assert server.requests == ["bytes=1000-"]


def test_range_ignored_restarts(server, sleeps, tmp_path):
    server.ranges = False
    dest = tmp_path / "f.bin"
    dest.with_name("f.bin.part").write_bytes(b"garbage" * 100)
    r = mgr(sleeps).download(server.url, dest, checksum=SHA, checksum_algorithm="sha256")
    assert not r.resumed and dest.read_bytes() == PAYLOAD


def test_416_complete_part_is_finalized(server, sleeps, tmp_path):
    dest = tmp_path / "f.bin"
    dest.with_name("f.bin.part").write_bytes(PAYLOAD)
    r = mgr(sleeps).download(server.url, dest, checksum=SHA, checksum_algorithm="sha256")
    assert dest.read_bytes() == PAYLOAD and r.resumed


def test_interrupted_then_resumed_via_retry(server, sleeps, tmp_path):
    server.cut_first = True
    dest = tmp_path / "f.bin"
    r = mgr(sleeps).download(server.url, dest, expected_size=len(PAYLOAD), checksum=SHA, checksum_algorithm="sha256")
    assert r.resumed and dest.read_bytes() == PAYLOAD and len(sleeps) == 1


def test_part_retained_when_retries_exhausted(server, sleeps, tmp_path):
    server.cut_first = True
    dest = tmp_path / "f.bin"
    with pytest.raises(DownloadError):
        mgr(sleeps, download_retries=0).download(server.url, dest, expected_size=len(PAYLOAD))
    assert not dest.exists() and 0 < dest.with_name("f.bin.part").stat().st_size < len(PAYLOAD)


def test_retry_503_then_success_with_backoff(server, sleeps, tmp_path):
    server.statuses = [503, 429]
    mgr(sleeps).download(server.url, tmp_path / "f")
    assert len(sleeps) == 2 and 1 <= sleeps[0] < 2 and 2 <= sleeps[1] < 3


def test_retries_exhausted(server, sleeps, tmp_path):
    server.statuses = [500] * 10
    with pytest.raises(DownloadError):
        mgr(sleeps, download_retries=2).download(server.url, tmp_path / "f")
    assert len(server.requests) == 3


@pytest.mark.parametrize("code", [401, 403])
def test_auth_no_retry_no_secret(server, sleeps, tmp_path, code):
    server.statuses = [code]
    with pytest.raises(AuthenticationError) as e:
        mgr(sleeps).download(server.url, tmp_path / "f")
    assert "SECRET" not in str(e.value) and not sleeps and len(server.requests) == 1


@pytest.mark.parametrize("code", [404, 410])
def test_not_found_no_retry(server, sleeps, tmp_path, code):
    server.statuses = [code]
    with pytest.raises(DownloadError) as e:
        mgr(sleeps).download(server.url, tmp_path / "f")
    assert e.value.retryable is False and not sleeps


def test_checksum_mismatch_deletes_part_and_fails(server, sleeps, tmp_path):
    dest = tmp_path / "f.bin"
    with pytest.raises(DownloadError, match="checksum"):
        mgr(sleeps, download_retries=1).download(server.url, dest, checksum="0" * 64, checksum_algorithm="sha256")
    assert not dest.exists() and not dest.with_name("f.bin.part").exists()
    assert len(server.requests) == 2


def test_size_cap_on_expected_size(server, sleeps, tmp_path):
    with pytest.raises(DownloadError) as e:
        mgr(sleeps, max_file_size_bytes=100).download(server.url, tmp_path / "f", expected_size=101)
    assert e.value.retryable is False and not server.requests


def test_size_cap_on_stream(server, sleeps, tmp_path):
    dest = tmp_path / "f.bin"
    with pytest.raises(DownloadError, match="limit") as e:
        mgr(sleeps, max_file_size_bytes=1024).download(server.url, dest)
    assert e.value.retryable is False and not dest.with_name("f.bin.part").exists()


def test_wrong_expected_size(server, sleeps, tmp_path):
    with pytest.raises(DownloadError) as e:
        mgr(sleeps).download(server.url, tmp_path / "f", expected_size=len(PAYLOAD) - 1)
    assert e.value.retryable is False


def test_refuse_overwrite_and_duplicate_skip(server, sleeps, tmp_path):
    dest = tmp_path / "f.bin"
    dest.write_bytes(b"different")
    with pytest.raises(DownloadError, match="refusing to overwrite") as e:
        mgr(sleeps).download(server.url, dest, checksum=SHA, checksum_algorithm="sha256")
    assert e.value.retryable is False and dest.read_bytes() == b"different" and not server.requests
    dest.write_bytes(PAYLOAD)
    r = mgr(sleeps).download(server.url, dest, checksum=SHA, checksum_algorithm="sha256")
    assert r.sha256 == SHA and not server.requests
    r = mgr(sleeps).download(server.url, dest, expected_size=len(PAYLOAD))  # size-only match
    assert not server.requests


def test_disk_space_check(server, sleeps, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.disk_usage", lambda p: SimpleNamespace(free=10))
    with pytest.raises(DownloadError, match="disk") as e:
        mgr(sleeps).download(server.url, tmp_path / "f", expected_size=1000)
    assert e.value.retryable is False and not server.requests


def test_progress_throttled_with_final_call(server, sleeps, tmp_path):
    calls = []
    mgr(sleeps).download(server.url, tmp_path / "f", progress=lambda d, t: calls.append((d, t)))
    assert calls[-1] == (len(PAYLOAD), len(PAYLOAD))
    assert 2 <= len(calls) <= 6  # ~1 MB chunks, not per-write
    assert [c[0] for c in calls] == sorted(c[0] for c in calls)


def test_fake_session_used(sleeps, tmp_path):
    class Resp:
        status_code, headers = 200, {"Content-Length": "3"}
        def iter_content(self, n): yield b"abc"
        def close(self): pass

    class Sess:
        def get(self, url, **kw):
            assert kw["timeout"] == 5
            return Resp()

    r = mgr(sleeps).download("http://example.invalid/x", tmp_path / "x", session=Sess())
    assert r.size_bytes == 3
