import ipaddress
import re
from urllib.parse import urlsplit


_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_NON_PUBLIC_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".svc",
    ".cluster.local",
    ".home.arpa",
    ".test",
    ".invalid",
)


def is_public_http_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return False
        parsed.port
    except ValueError:
        return False

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(_NON_PUBLIC_SUFFIXES):
        return False

    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        labels = host.split(".")
        return len(labels) >= 2 and all(_HOST_LABEL.fullmatch(label) for label in labels)
