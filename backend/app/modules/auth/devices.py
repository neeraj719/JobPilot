"""Friendly device labels for the "Sessions and devices" list.

A deliberately small parser: the label is a hint shown next to a session ("Chrome on
Windows") so the user can recognise their own devices, not an identity claim. The user
agent is client-supplied, so nothing is ever decided from it. Order matters: Edge and
Opera also say "Chrome", Chrome also says "Safari", every iOS browser says "Safari".
"""
from __future__ import annotations

import re

_BROWSERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Edge", re.compile(r"\bEdg(?:e|A|iOS)?/", re.I)),
    ("Opera", re.compile(r"\b(?:OPR|Opera)/", re.I)),
    ("Samsung Internet", re.compile(r"\bSamsungBrowser/", re.I)),
    ("Firefox", re.compile(r"\b(?:Firefox|FxiOS)/", re.I)),
    ("Chrome", re.compile(r"\b(?:Chrome|CriOS)/", re.I)),
    ("Safari", re.compile(r"\bVersion/[\d.]+.*\bSafari/", re.I)),
)

_SYSTEMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("iPhone", re.compile(r"\biPhone\b", re.I)),
    ("iPad", re.compile(r"\biPad\b", re.I)),
    ("Android", re.compile(r"\bAndroid\b", re.I)),
    ("ChromeOS", re.compile(r"\bCrOS\b", re.I)),
    ("Windows", re.compile(r"\bWindows\b", re.I)),
    ("macOS", re.compile(r"\bMac OS X\b|\bMacintosh\b", re.I)),
    ("Linux", re.compile(r"\bLinux\b", re.I)),
)

UNKNOWN_DEVICE = "Unknown device"


def _first(patterns: tuple[tuple[str, re.Pattern[str]], ...], user_agent: str) -> str | None:
    for name, pattern in patterns:
        if pattern.search(user_agent):
            return name
    return None


def device_label(user_agent: str | None) -> str:
    """``"Chrome on Windows"``, ``"Safari on iPhone"``, ``"Firefox"``, ``"Unknown device"``."""
    if not user_agent:
        return UNKNOWN_DEVICE
    browser = _first(_BROWSERS, user_agent)
    system = _first(_SYSTEMS, user_agent)
    if browser and system:
        return f"{browser} on {system}"
    if browser:
        return browser
    if system:
        return f"Browser on {system}"
    return UNKNOWN_DEVICE
