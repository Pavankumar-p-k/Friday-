from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@dataclass(frozen=True)
class DashboardUser:
    username: str


class DashboardAuthError(Exception):
    pass


class DashboardAuthManager:
    def __init__(self) -> None:
        self.enabled = _parse_bool_env("FRIDAY_DASHBOARD_AUTH_ENABLED", True)
        self.username = os.getenv("FRIDAY_DASHBOARD_AUTH_USERNAME", "admin").strip() or "admin"
        self.secret = os.getenv("FRIDAY_DASHBOARD_AUTH_SECRET", "").strip()
        if not self.secret:
            self.secret = "friday-dashboard-dev-secret-change-me"
        self.ttl_sec = max(60, _parse_int_env("FRIDAY_DASHBOARD_AUTH_TTL_SEC", 8 * 60 * 60))
        self.password_hash = self._resolve_password_hash()

    def issue_token(self, username: str, password: str) -> dict[str, Any]:
        if not self.enabled:
            user = DashboardUser(username=self.username)
            return {"access_token": self._sign_token(user), "token_type": "bearer", "expires_in": self.ttl_sec}

        if username != self.username:
            raise DashboardAuthError("Invalid username or password.")
        if not self.verify_password(password):
            raise DashboardAuthError("Invalid username or password.")

        user = DashboardUser(username=self.username)
        return {"access_token": self._sign_token(user), "token_type": "bearer", "expires_in": self.ttl_sec}

    def verify_token(self, token: str) -> DashboardUser:
        if not token:
            raise DashboardAuthError("Missing token.")
        parts = token.split(".")
        if len(parts) != 3:
            raise DashboardAuthError("Malformed token.")
        header_segment, payload_segment, signature_segment = parts
        signed = f"{header_segment}.{payload_segment}".encode("ascii")
        expected = _b64url_encode(hmac.new(self.secret.encode("utf-8"), signed, hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature_segment):
            raise DashboardAuthError("Invalid token signature.")

        try:
            payload = json.loads(_b64url_decode(payload_segment).decode("utf-8"))
        except Exception as exc:
            raise DashboardAuthError("Invalid token payload.") from exc

        exp = int(payload.get("exp", 0))
        if int(_utc_now().timestamp()) >= exp:
            raise DashboardAuthError("Token expired.")

        username = str(payload.get("sub", "")).strip()
        if not username:
            raise DashboardAuthError("Invalid token subject.")
        return DashboardUser(username=username)

    def verify_password(self, password: str) -> bool:
        return _verify_password(password, self.password_hash)

    def _resolve_password_hash(self) -> str:
        hash_from_env = os.getenv("FRIDAY_DASHBOARD_AUTH_PASSWORD_HASH", "").strip()
        if hash_from_env:
            return hash_from_env

        plain_password = os.getenv("FRIDAY_DASHBOARD_AUTH_PASSWORD", "").strip()
        if plain_password:
            return _hash_password(plain_password)

        # Explicit default for local scaffolding only.
        return _hash_password("change-me")

    def _sign_token(self, user: DashboardUser) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        now_ts = int(_utc_now().timestamp())
        payload = {
            "sub": user.username,
            "iat": now_ts,
            "exp": int((_utc_now() + timedelta(seconds=self.ttl_sec)).timestamp()),
            "jti": secrets.token_hex(8),
        }
        header_segment = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signed = f"{header_segment}.{payload_segment}".encode("ascii")
        signature_segment = _b64url_encode(
            hmac.new(self.secret.encode("utf-8"), signed, hashlib.sha256).digest()
        )
        return f"{header_segment}.{payload_segment}.{signature_segment}"


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = 120_000
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algo, rounds_raw, salt, hex_digest = encoded.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        rounds = int(rounds_raw)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        rounds,
    ).hex()
    return hmac.compare_digest(candidate, hex_digest)


def _parse_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default
