"""Helpers shared by plugins that call an outside service for the user (RT, Social).

Each of those plugins keeps a connection config in the user's own Drive under
``plugins/<id>/config.json``, with its secrets Fernet-encrypted by the server seal
key, and fetches URLs the user supplied. The encryption, the Drive folder layout
and the public-address check live here once, so a fix to any of them reaches
every plugin.
"""

import ipaddress
import json
import os
import socket
from urllib.parse import urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool

import mcp_tokens
from transports.google_drive_transport import GoogleDriveTransport

ENC_PREFIX = "fernet:"
CONFIG_FILE = "config.json"


def encrypt_secret(value):
    """Encrypt a secret for storage in the user's Drive, or '' for empty."""
    if not value:
        return ""
    return ENC_PREFIX + Fernet(mcp_tokens.seal_key()).encrypt(value.encode()).decode()


def decrypt_secret(value):
    """Decrypt a stored secret.

    Returns '' if the seal key has rotated (the user re-enters the secret) and
    passes a legacy plaintext value through unchanged.
    """
    if not value or not value.startswith(ENC_PREFIX):
        return value or ""
    try:
        return Fernet(mcp_tokens.seal_key()).decrypt(value[len(ENC_PREFIX) :].encode()).decode()
    except InvalidToken:
        return ""


def find_or_create_folder(service, parent_id, name):
    """ID of the Drive folder ``name`` under ``parent_id``, created if missing."""
    query = (
        f"name='{name}' and '{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    files = service.files().list(q=query, spaces="drive", fields="files(id)").execute().get("files", [])
    if files:
        return files[0]["id"]
    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    return service.files().create(body=metadata, fields="id").execute()["id"]


def ensure_plugin_folder(service, root_folder_id, plugin_id):
    """ID of ``plugins/<plugin_id>/`` under the user's Acquacotta folder."""
    plugins_id = find_or_create_folder(service, root_folder_id, "plugins")
    return find_or_create_folder(service, plugins_id, plugin_id)


def config_transport(service, root_folder_id, plugin_id):
    """A Drive transport rooted at the plugin's ``plugins/<plugin_id>/`` folder."""
    return GoogleDriveTransport(service, ensure_plugin_folder(service, root_folder_id, plugin_id))


def save_config(service, root_folder_id, plugin_id, clean, secret_fields):
    """Write a validated config to ``plugins/<plugin_id>/config.json``, secrets encrypted.

    Args:
        service: the user's Google Drive API client.
        root_folder_id: the user's Acquacotta folder in that Drive.
        plugin_id: the plugin's id, which names its folder under ``plugins/``.
        clean: the validated config dict, secrets in plaintext.
        secret_fields: names of the keys in ``clean`` to encrypt before writing.

    Returns:
        ``clean`` unmodified, secrets in plaintext: the caller masks them before
        anything reaches a client.
    """
    to_store = dict(clean)
    for field in secret_fields:
        to_store[field] = encrypt_secret(clean[field])
    transport = config_transport(service, root_folder_id, plugin_id)
    transport.upload_file(CONFIG_FILE, json.dumps(to_store, indent=2, ensure_ascii=False))
    return clean


def resolved_ips(host):
    """Every address ``host`` resolves to (an IP literal resolves to itself, no DNS).

    Raises ValueError if the name cannot be resolved.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"host '{host}' could not be resolved") from exc
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def is_public_ip(ip):
    """True only for globally routable unicast addresses: the SSRF test.

    ``is_global`` is an allowlist, so loopback, private, link-local (cloud
    metadata), carrier-grade NAT (100.64/10), documentation and reserved ranges
    all fail it. An IPv4-mapped IPv6 address is judged as the IPv4 it carries.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def is_public_host(host):
    """True if every address ``host`` resolves to is publicly routable."""
    return all(is_public_ip(ip) for ip in resolved_ips(host))


def allowed_hosts(allowlist_env):
    """Hosts the operator listed in the ``allowlist_env`` variable (comma-separated)."""
    raw = os.environ.get(allowlist_env, "") if allowlist_env else ""
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def check_destination(url, allowlist_env, strict=False):
    """Raise ValueError unless the server may fetch ``url``.

    The URL must be http(s). A host listed in the ``allowlist_env`` variable
    (comma-separated) is trusted as is, which is how an operator lets the
    server reach a private instance. With ``strict``, a set allowlist is the
    only way in; otherwise an unlisted host must resolve to public addresses.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must be http(s)")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("URL has no host")
    allowed = allowed_hosts(allowlist_env)
    if host in allowed:
        return
    if strict and allowed:
        raise ValueError(f"host '{host}' is not in the {allowlist_env} allowlist")
    if not is_public_host(host):
        hint = f"; set {allowlist_env} to allow it" if allowlist_env else ""
        raise ValueError(f"host '{host}' resolves to a non-public address{hint}")


class NonPublicPeerError(OSError):
    """The connection reached a non-public address (DNS changed after the check)."""


def require_public_peer(sock):
    """Close ``sock`` and raise unless it is connected to a public address.

    ``check_destination`` resolves the name before the request, and the HTTP
    client resolves it again to connect; a hostile DNS server can answer public
    the first time and 169.254.169.254 the second (DNS rebinding). Checking the
    address the socket actually connected to closes that gap.
    """
    peer = ipaddress.ip_address(sock.getpeername()[0])
    if not is_public_ip(peer):
        sock.close()
        raise NonPublicPeerError(f"connection to non-public address {peer} refused")
    return sock


class _PublicHTTPConnection(HTTPConnection):
    def _new_conn(self):
        return require_public_peer(super()._new_conn())


class _PublicHTTPSConnection(HTTPSConnection):
    def _new_conn(self):
        return require_public_peer(super()._new_conn())


class _PublicHTTPPool(HTTPConnectionPool):
    ConnectionCls = _PublicHTTPConnection


class _PublicHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _PublicHTTPSConnection


class _PublicOnlyAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {"http": _PublicHTTPPool, "https": _PublicHTTPSPool}


def session_for(url, allowlist_env):
    """A requests session for fetching ``url``, after ``check_destination``.

    An operator-allowlisted host gets a plain session (it may be private by
    design); anything else gets a session that refuses to connect to a
    non-public address. Proxy environment variables are ignored so the check
    applies to the real destination, not to a proxy.
    """
    session = requests.Session()
    session.trust_env = False
    if (urlparse(url).hostname or "").lower() not in allowed_hosts(allowlist_env):
        adapter = _PublicOnlyAdapter()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
    return session
