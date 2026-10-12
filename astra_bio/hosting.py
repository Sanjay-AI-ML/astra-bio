"""Explicit deployment hosts and browser origins, preserving local defaults."""
import os
from urllib.parse import urlsplit

LOCAL_ORIGINS = {"http://127.0.0.1:8501", "http://localhost:8501",
                 "http://127.0.0.1:5173", "http://localhost:5173"}


def hosting_settings():
    hosts = {"127.0.0.1", "localhost", "[::1]"}
    hosts.update(value.strip() for value in os.getenv("ASTRA_ALLOWED_HOSTS", "").split(",") if value.strip())
    render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_host:
        hosts.add(render_host)
    origins = set(LOCAL_ORIGINS)
    origins.update(value.strip().rstrip("/") for value in os.getenv("ASTRA_ALLOWED_ORIGINS", "").split(",") if value.strip())
    if render_host:
        origins.add("https://" + render_host)
    for origin in origins:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("ASTRA_ALLOWED_ORIGINS must contain comma-separated HTTP(S) origins without paths.")
    if "*" in hosts:
        raise ValueError("ASTRA_ALLOWED_HOSTS must list explicit hosts, not '*'.")
    return sorted(hosts), origins
