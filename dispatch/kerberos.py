"""Kerberos pre-flight helpers.

TTL parsing expects MIT Kerberos `klist` output with a header line:
`Valid starting       Expires              Service principal`, followed by at
least one ticket row whose first two columns are `MM/DD/YYYY HH:MM:SS` start
and `MM/DD/YYYY HH:MM:SS` expiry timestamps.
"""

from __future__ import annotations

import logging
from datetime import datetime

from . import process

logger = logging.getLogger("dispatch.kerberos")


async def has_ticket() -> bool:
    try:
        rc, _stdout, _stderr = await process.run_exec("klist", "-s", timeout=5)
        return rc == 0
    except (OSError, FileNotFoundError):
        logger.warning("klist not found on PATH")
        return False


async def ticket_ttl_seconds() -> int | None:
    try:
        rc, stdout, _stderr = await process.run_exec("klist", timeout=5)
    except (OSError, FileNotFoundError):
        logger.warning("klist not found on PATH; Kerberos unavailable")
        return None
    if rc != 0:
        return None
    return parse_ttl_seconds(stdout)


def parse_ttl_seconds(klist_output: str, now: datetime | None = None) -> int | None:
    current = now or datetime.now()
    for line in klist_output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            expires = datetime.strptime(f"{parts[2]} {parts[3]}", "%m/%d/%Y %H:%M:%S")
        except ValueError:
            continue
        return max(0, int((expires - current).total_seconds()))
    return None
