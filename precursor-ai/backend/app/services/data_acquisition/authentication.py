"""Earthdata Login for downloads. Catalog search is anonymous and never touches this.

Credentials come from Settings (.env) or ~/.netrc. They are SecretStr in Settings and are only
unwrapped at the earthaccess call boundary; no message, exception or log line contains them.
"""
from __future__ import annotations

import logging
import netrc
import os
import threading
from collections.abc import Callable
from typing import Any, Literal

import requests

from app.core.config import Settings
from app.services.data_acquisition.types import AuthenticationError

log = logging.getLogger(__name__)

EDL_HOST = "urs.earthdata.nasa.gov"
_ENV_USER, _ENV_PASS = "EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"
_env_lock = threading.Lock()  # os.environ is process-global; serialise the temporary override

Status = Literal["configured", "missing", "failed"]


def _earthaccess_login(strategy: str) -> Any:
    import earthaccess

    return earthaccess.login(strategy=strategy)


def _netrc_has_entry() -> bool:
    try:
        from earthaccess.auth import netrc_path

        return netrc.netrc(str(netrc_path())).authenticators(EDL_HOST) is not None
    except Exception:  # missing/unreadable/unparseable file all mean "no entry"
        return False


class EarthdataAuthenticationService:
    def __init__(self, settings: Settings, *, login_fn: Callable[[str], Any] | None = None) -> None:
        self._settings = settings
        self._login_fn = login_fn or _earthaccess_login
        self._lock = threading.Lock()
        self._logged_in = False
        self._failed = False

    def _has_credentials(self) -> bool:
        return self._settings.has_earthdata_credentials or _netrc_has_entry()

    def status(self) -> Status:
        """No network access: a login is only attempted by login()/get_session()."""
        if self._logged_in:
            return "configured"
        if self._failed:
            return "failed"
        return "configured" if self._has_credentials() else "missing"

    def login(self) -> bool:
        with self._lock:
            return self._login_locked()

    def _login_locked(self) -> bool:
        if self._logged_in:
            return True
        s = self._settings
        if not self._has_credentials():
            raise AuthenticationError(
                "Earthdata credentials are not configured: set EARTHDATA_USERNAME and EARTHDATA_PASSWORD "
                "in .env or add a urs.earthdata.nasa.gov entry to ~/.netrc."
            )
        try:
            if s.has_earthdata_credentials:
                with _env_lock:
                    saved = {k: os.environ.get(k) for k in (_ENV_USER, _ENV_PASS)}
                    os.environ[_ENV_USER] = s.earthdata_username.get_secret_value()  # type: ignore[union-attr]
                    os.environ[_ENV_PASS] = s.earthdata_password.get_secret_value()  # type: ignore[union-attr]
                    try:
                        auth = self._login_fn("environment")
                    finally:
                        for k, v in saved.items():
                            if v is None:
                                os.environ.pop(k, None)
                            else:
                                os.environ[k] = v
            else:
                auth = self._login_fn("netrc")
            ok = bool(getattr(auth, "authenticated", auth))
        except Exception as exc:
            self._failed = True
            # type name only: upstream messages can echo request details
            raise AuthenticationError(f"Earthdata Login failed ({type(exc).__name__}). Check the credentials.") from None
        if not ok:
            self._failed = True
            raise AuthenticationError("Earthdata Login was rejected. Check the credentials.")
        self._failed = False
        self._logged_in = True
        log.info("Earthdata Login succeeded")
        return True

    def get_session(self) -> requests.Session:
        """Authenticated session for data downloads; logs in lazily (once, thread-safe)."""
        with self._lock:
            self._login_locked()
        import earthaccess

        return earthaccess.get_requests_https_session()
