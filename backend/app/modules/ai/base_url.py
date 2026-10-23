"""Validation of user-supplied model-server addresses (Ollama, OpenAI-compatible servers).

A base URL makes *this server* send requests to an address a user typed, so it is checked
before it is stored and again before every client is built:

* ``https://`` or ``http://`` only, a host, no user-info, no query or fragment;
* every address the host resolves to is checked: link-local (``169.254.0.0/16``,
  ``fe80::/10``) — which is where cloud metadata services live — multicast, reserved and
  unspecified addresses are always refused;
* loopback and private-network addresses (LM Studio on ``localhost``, a GPU box on the LAN)
  are accepted only while ``AI_ALLOW_LOCAL_BASE_URLS`` is on. Plain ``http`` is accepted
  only for such local addresses: a public server must use ``https``.

Trade-off (documented in the report): on a single-user or trusted deployment, reaching the
user's own local server is the feature. On a multi-tenant deployment an admin should turn
``AI_ALLOW_LOCAL_BASE_URLS`` off, because a user could otherwise make the server probe its
internal network. DNS can change between this check and the request (rebinding); the check
is repeated whenever a client is built, which narrows but does not close that window.
"""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

from app.core.config import settings
from app.core.exceptions import ValidationFailed

Resolver = Callable[[str], list[str]]

_METADATA_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}


def _default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({info[4][0] for info in infos})


_resolver: Resolver = _default_resolver


def set_resolver(resolver: Resolver | None) -> None:
    """Tests swap DNS for a stub."""
    global _resolver
    _resolver = resolver or _default_resolver


def _fail(message: str) -> ValidationFailed:
    return ValidationFailed(message, code="invalid_base_url")


def _classify(address: str) -> str:
    """``public`` | ``local`` (loopback/private) | ``forbidden``."""
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return "forbidden"
    if ip.is_loopback or ip.is_private:
        return "local"
    return "public"


def validate_base_url(raw: str | None, *, resolve: bool = True) -> str:
    """The normalised URL (no trailing slash) or :class:`ValidationFailed` ``invalid_base_url``."""
    value = (raw or "").strip()
    if not value:
        raise _fail("Enter the server's base URL, for example http://localhost:1234/v1.")
    if len(value) > 500:
        raise _fail("The base URL is too long.")
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise _fail("The base URL must start with http:// or https://.")
    if parts.username or parts.password or "@" in parts.netloc:
        raise _fail("Do not put credentials in the URL; use the API key field.")
    if parts.query or parts.fragment:
        raise _fail("The base URL cannot contain a query string or fragment.")
    host = (parts.hostname or "").strip().lower()
    if not host:
        raise _fail("The base URL has no host name.")
    if host in _METADATA_HOSTS:
        raise _fail("That address is not allowed.")
    try:
        _ = parts.port
    except ValueError as exc:
        raise _fail("The port in the base URL is not valid.") from exc

    if resolve:
        try:
            addresses = [host] if _is_ip(host) else _resolver(host)
        except OSError as exc:
            raise _fail(f"Could not resolve {host!r}. Check the address.") from exc
        if not addresses:
            raise _fail(f"Could not resolve {host!r}. Check the address.")
        kinds = {_classify(address) for address in addresses}
        if "forbidden" in kinds:
            raise _fail("That address is not allowed (link-local and metadata addresses are refused).")
        if "local" in kinds and not settings.AI_ALLOW_LOCAL_BASE_URLS:
            raise _fail("This server does not allow local or private-network model servers.")
        if scheme == "http" and kinds != {"local"}:
            raise _fail("Use https:// for a server on the internet (plain http is only allowed for local servers).")

    path = parts.path.rstrip("/")
    return urlunsplit((scheme, parts.netloc, path, "", ""))


def is_local_url(raw: str | None) -> bool:
    """Whether every address of the URL's host is loopback/private (never raises)."""
    try:
        host = (urlsplit(raw or "").hostname or "").lower()
        if not host:
            return False
        addresses = [host] if _is_ip(host) else _resolver(host)
        return bool(addresses) and all(_classify(a) == "local" for a in addresses)
    except Exception:  # noqa: BLE001
        return False


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


__all__ = ["is_local_url", "set_resolver", "validate_base_url"]
