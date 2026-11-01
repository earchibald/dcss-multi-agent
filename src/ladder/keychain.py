"""Secrets live in macOS Keychain under one service; config only names the item."""

import secrets as _secrets

import keyring

SERVICE = "dcss-ladder"


def get(account: str) -> str | None:
    return keyring.get_password(SERVICE, account)


def set(account: str, value: str) -> None:
    keyring.set_password(SERVICE, account, value)


def dcss_account(username: str) -> str:
    return f"dcss-account/{username}"


def get_or_create_dcss_password(username: str) -> tuple[str, bool]:
    """Return (password, created). Creates and stores a random password on first use."""
    account = dcss_account(username)
    existing = get(account)
    if existing:
        return existing, False
    password = _secrets.token_urlsafe(24)
    set(account, password)
    return password, True


def get_item(service: str, account: str | None) -> str | None:
    """Any Keychain generic password, for profiles that name their own item."""
    return keyring.get_password(service, account or "")
