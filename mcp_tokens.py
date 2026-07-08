"""Acquacotta MCP access tokens — stateless, sealed bearer credentials.

A token is an encrypted+authenticated blob that carries everything the MCP
server needs to reach one user's storage: their Google refresh token and their
Drive folder id. The server holds no copy — it decrypts a token in memory per
request, uses it, and discards it (constitution I & II).

Format: ``aqc_v1.<fernet-token>`` where the Fernet token is the encrypted JSON
payload ``{v, email, refresh_token, folder_id, issued_at}``. Fernet provides
the confidentiality + tamper detection; ``issued_at`` (unix seconds) is checked
against the per-user revocation epoch stored in the user's own Drive.

Sealing key: ``MCP_TOKEN_SEAL_KEY`` (a urlsafe-base64 32-byte Fernet key),
REQUIRED in production. In development (``FLASK_ENV=development``) it may be
derived from ``FLASK_SECRET_KEY`` so the Flask and MCP processes agree without
extra config; outside development an unset key fails closed. Rotating the key is
the global panic-revoke.
"""

import base64
import hashlib
import json
import os
import time

from cryptography.fernet import Fernet, InvalidToken

TOKEN_PREFIX = "aqc_v1."
TOKEN_VERSION = 1


class TokenError(Exception):
    """Raised when a token is missing, malformed, tampered with, or revoked."""


def _seal_key():
    """Return the Fernet key that protects sealed refresh tokens.

    In production ``MCP_TOKEN_SEAL_KEY`` MUST be set explicitly (a high-entropy,
    independently rotatable key). Deriving it from ``FLASK_SECRET_KEY`` is a
    convenience allowed ONLY in development (``FLASK_ENV=development``); outside
    development we fail closed rather than couple token security to the Flask
    secret.
    """
    explicit = os.environ.get("MCP_TOKEN_SEAL_KEY")
    if explicit:
        return explicit.encode() if isinstance(explicit, str) else explicit
    if os.environ.get("FLASK_ENV") != "development":
        raise TokenError(
            "MCP_TOKEN_SEAL_KEY must be set explicitly (it is only derived from FLASK_SECRET_KEY in development)"
        )
    secret = os.environ.get("FLASK_SECRET_KEY")
    if not secret:
        raise TokenError("Set MCP_TOKEN_SEAL_KEY (or FLASK_SECRET_KEY for local development)")
    digest = hashlib.sha256(secret.encode()).digest()  # 32 bytes
    return base64.urlsafe_b64encode(digest)


def seal(email, refresh_token, folder_id, issued_at=None):
    """Seal credentials into an ``aqc_v1.`` bearer token string."""
    if not refresh_token:
        raise TokenError("Cannot mint a token without a refresh_token")
    if not folder_id:
        raise TokenError("Cannot mint a token without a folder_id")
    payload = {
        "v": TOKEN_VERSION,
        "email": email,
        "refresh_token": refresh_token,
        "folder_id": folder_id,
        "issued_at": int(issued_at if issued_at is not None else time.time()),
    }
    blob = Fernet(_seal_key()).encrypt(json.dumps(payload).encode())
    return TOKEN_PREFIX + blob.decode()


def unseal(token):
    """Decrypt and validate a token's cryptography; return its payload dict.

    Raises :class:`TokenError` if the token is missing, malformed, or tampered
    with. Does NOT check the revocation epoch — that requires the user's state
    and is done by the caller via :func:`is_revoked`.
    """
    if not token or not token.startswith(TOKEN_PREFIX):
        raise TokenError("Malformed token")
    blob = token[len(TOKEN_PREFIX) :].encode()
    try:
        raw = Fernet(_seal_key()).decrypt(blob)
    except InvalidToken as exc:
        raise TokenError("Invalid or tampered token") from exc
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise TokenError("Corrupt token payload") from exc
    if payload.get("v") != TOKEN_VERSION:
        raise TokenError("Unsupported token version")
    for field in ("email", "refresh_token", "folder_id", "issued_at"):
        if not payload.get(field):
            raise TokenError(f"Token missing {field}")
    return payload


def is_revoked(payload, mcp_state):
    """Return True if the token is disabled or predates the revocation epoch."""
    if not mcp_state.get("enabled"):
        return True
    return int(payload.get("issued_at", 0)) < int(mcp_state.get("epoch", 0))
