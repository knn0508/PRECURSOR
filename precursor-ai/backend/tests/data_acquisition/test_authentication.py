import logging
import os

import pytest

from app.core.config import Settings
from app.services.data_acquisition import authentication as auth_mod
from app.services.data_acquisition.authentication import EarthdataAuthenticationService
from app.services.data_acquisition.types import AuthenticationError

SECRET_U, SECRET_P = "uuser-9f3", "pp@ss-7a1"


def settings(creds=True):
    kw = {"earthdata_username": SECRET_U, "earthdata_password": SECRET_P} if creds else {}
    return Settings(_env_file=None, **kw)


@pytest.fixture(autouse=True)
def no_netrc(monkeypatch):
    monkeypatch.setattr(auth_mod, "_netrc_has_entry", lambda: False)
    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)


class Ok:
    authenticated = True


def test_missing_then_login_raises_without_secrets():
    svc = EarthdataAuthenticationService(settings(False), login_fn=lambda s: Ok())
    assert svc.status() == "missing"
    with pytest.raises(AuthenticationError):
        svc.login()
    with pytest.raises(AuthenticationError):
        svc.get_session()


def test_configured_by_settings_and_by_netrc(monkeypatch):
    assert EarthdataAuthenticationService(settings()).status() == "configured"
    monkeypatch.setattr(auth_mod, "_netrc_has_entry", lambda: True)
    assert EarthdataAuthenticationService(settings(False)).status() == "configured"


def test_login_passes_settings_via_temporary_env_and_restores():
    seen = {}

    def fn(strategy):
        seen.update(strategy=strategy, u=os.environ["EARTHDATA_USERNAME"], p=os.environ["EARTHDATA_PASSWORD"])
        return Ok()

    svc = EarthdataAuthenticationService(settings(), login_fn=fn)
    assert svc.login() is True
    assert seen == {"strategy": "environment", "u": SECRET_U, "p": SECRET_P}
    assert "EARTHDATA_PASSWORD" not in os.environ
    assert svc.status() == "configured"


def test_login_uses_netrc_strategy_when_no_settings(monkeypatch):
    monkeypatch.setattr(auth_mod, "_netrc_has_entry", lambda: True)
    calls = []
    svc = EarthdataAuthenticationService(settings(False), login_fn=lambda s: calls.append(s) or Ok())
    svc.login()
    svc.login()  # already logged in: no second call
    assert calls == ["netrc"]


@pytest.mark.parametrize("fail", ["raise", "false"])
def test_login_failure_sets_failed_and_leaks_nothing(fail, caplog, monkeypatch):
    def fn(strategy):
        if fail == "raise":
            raise RuntimeError(f"bad creds {SECRET_U}:{SECRET_P}")
        return type("A", (), {"authenticated": False})()

    svc = EarthdataAuthenticationService(settings(), login_fn=fn)
    with caplog.at_level(logging.DEBUG), pytest.raises(AuthenticationError) as ei:
        svc.login()
    assert svc.status() == "failed"
    for secret in (SECRET_U, SECRET_P):
        assert secret not in str(ei.value) and secret not in repr(ei.value.__cause__)
        assert secret not in caplog.text
    assert "EARTHDATA_PASSWORD" not in os.environ


def test_get_session_logs_in_lazily(monkeypatch):
    import earthaccess

    sentinel = object()
    monkeypatch.setattr(earthaccess, "get_requests_https_session", lambda: sentinel)
    svc = EarthdataAuthenticationService(settings(), login_fn=lambda s: Ok())
    assert svc.get_session() is sentinel
