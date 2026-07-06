"""Tests for mcp_tokens.py — sealing, unsealing, tamper detection, revocation."""

import os

import pytest

# Ensure a known sealing key basis before import (mirrors conftest).
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key")

import mcp_tokens


class TestSealUnseal:
    def test_round_trip_returns_payload(self):
        token = mcp_tokens.seal("user@example.com", "refresh-abc", "folder-123", issued_at=1000)
        assert token.startswith("aqc_v1.")
        payload = mcp_tokens.unseal(token)
        assert payload["email"] == "user@example.com"
        assert payload["refresh_token"] == "refresh-abc"
        assert payload["folder_id"] == "folder-123"
        assert payload["issued_at"] == 1000

    def test_seal_requires_refresh_token(self):
        with pytest.raises(mcp_tokens.TokenError):
            mcp_tokens.seal("u@e.com", "", "folder-123")

    def test_seal_requires_folder_id(self):
        with pytest.raises(mcp_tokens.TokenError):
            mcp_tokens.seal("u@e.com", "refresh-abc", None)

    def test_missing_prefix_rejected(self):
        with pytest.raises(mcp_tokens.TokenError):
            mcp_tokens.unseal("not-a-token")

    def test_empty_token_rejected(self):
        with pytest.raises(mcp_tokens.TokenError):
            mcp_tokens.unseal("")

    def test_tampered_blob_rejected(self):
        token = mcp_tokens.seal("u@e.com", "refresh-abc", "folder-123")
        tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
        with pytest.raises(mcp_tokens.TokenError):
            mcp_tokens.unseal(tampered)

    def test_key_rotation_invalidates_token(self, monkeypatch):
        token = mcp_tokens.seal("u@e.com", "refresh-abc", "folder-123")
        # Rotate the sealing key — the global panic-revoke.
        from cryptography.fernet import Fernet

        monkeypatch.setenv("MCP_TOKEN_SEAL_KEY", Fernet.generate_key().decode())
        with pytest.raises(mcp_tokens.TokenError):
            mcp_tokens.unseal(token)


class TestRevocation:
    def _payload(self, issued_at):
        return {"email": "u@e.com", "refresh_token": "r", "folder_id": "f", "issued_at": issued_at, "v": 1}

    def test_enabled_and_current_not_revoked(self):
        assert mcp_tokens.is_revoked(self._payload(2000), {"enabled": True, "epoch": 1000}) is False

    def test_disabled_is_revoked(self):
        assert mcp_tokens.is_revoked(self._payload(2000), {"enabled": False, "epoch": 1000}) is True

    def test_pre_epoch_token_is_revoked(self):
        assert mcp_tokens.is_revoked(self._payload(500), {"enabled": True, "epoch": 1000}) is True

    def test_issued_at_equal_epoch_not_revoked(self):
        assert mcp_tokens.is_revoked(self._payload(1000), {"enabled": True, "epoch": 1000}) is False
