"""Infrastructure error classification.

The hard rule, from docs/proposal-infra-error-handling.md §2:

    **Content wrong != infra broken.**

A run that produced a bad answer, called the wrong tool, or tripped a mock 4xx
is *experiment signal* — that is what the matrix exists to measure. A run that
died because the disk filled or the API key expired measured nothing, and
recording it as a packaging failure is a lie that survives into the report.

The 2026-08-06 `matrix-40` run is the worked example: 28 D1 cells hit ENOSPC in
a sandbox write, were graded ``fail``, and dragged the D1-vs-A1 contrast down by
several points. Nothing in the ledger distinguished them from real failures.

Classification reads **only** signals that cannot be forged by a payload
(§2, "classifier inputs (unsafe)"): errno, exception type, and typed provider
codes. It never matches on response text — a tool result that says
"unauthorized" is the mock API doing its job, not our credentials expiring.
"""

from __future__ import annotations

import errno
import socket
import subprocess
from enum import StrEnum


class ErrorKind(StrEnum):
    """Why a run failed, when it failed for reasons outside the arm under test.

    Absent (``None`` on the row) means the run is Layer 0 — experiment signal,
    counted in packaging rates like any other outcome.
    """

    #: Layer 2. Disk full, results path unwritable. The ledger cannot be trusted.
    DISK = "disk"
    #: Layer 2. Invalid or expired credentials on the provider or MCP gateway.
    AUTH = "auth"
    #: Layer 2. Quota exhausted, billing hard limit, prepaid credit gone.
    BILLING = "billing"
    #: Layer 3. Provider or gateway 429.
    RATE_LIMIT = "rate_limit"
    #: Layer 3. Socket or provider timeout.
    TIMEOUT = "timeout"
    #: Layer 3. DNS blip, connection reset, transient unreachability.
    NETWORK = "network"
    #: Layer 3. Provider 5xx / overload.
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    #: Layer 4. The mock rig or MCP server died, not the LLM path.
    TARGET_UNAVAILABLE = "target_unavailable"
    #: Layer 4. JSON-RPC structural fault, failed handshake, tool-list drift.
    PROTOCOL = "protocol"
    #: Layer 5. Unclassifiable. Never fail-fast on this — §2 prefers false
    #: negatives on abort over false positives.
    UNKNOWN = "unknown"


#: Kinds that abort the matrix on first sight (§8). Continuing past these either
#: burns money on cells that cannot succeed or writes results that cannot be
#: trusted. `unknown` is deliberately absent.
FATAL = frozenset({ErrorKind.DISK, ErrorKind.AUTH, ErrorKind.BILLING})

#: Kinds whose rows a `--resume` should re-run rather than skip. Every infra
#: kind qualifies: none of them measured the arm, so none of them is data. The
#: distinction from FATAL is *when* we stop, not *whether* the cell is void.
RETRYABLE = frozenset(ErrorKind)

#: Provider SDK error codes/types, which are typed fields rather than prose and
#: so are safe to match on (§2).
_PROVIDER_CODES = {
    "insufficient_quota": ErrorKind.BILLING,
    "billing_hard_limit_reached": ErrorKind.BILLING,
    "invalid_api_key": ErrorKind.AUTH,
    "authentication_error": ErrorKind.AUTH,
    "permission_denied": ErrorKind.AUTH,
    "rate_limit_exceeded": ErrorKind.RATE_LIMIT,
}

_STATUS_KINDS = {
    401: ErrorKind.AUTH,
    403: ErrorKind.AUTH,
    402: ErrorKind.BILLING,
    429: ErrorKind.RATE_LIMIT,
    500: ErrorKind.PROVIDER_UNAVAILABLE,
    502: ErrorKind.PROVIDER_UNAVAILABLE,
    503: ErrorKind.PROVIDER_UNAVAILABLE,
    504: ErrorKind.TIMEOUT,
}

#: errno values that mean "this machine cannot persist results", not "the run
#: went badly". ENOSPC is the one that started all this.
_DISK_ERRNOS = frozenset({errno.ENOSPC, errno.EDQUOT, errno.EROFS, errno.EACCES,
                          errno.EPERM, errno.EFBIG, errno.EMFILE, errno.ENFILE})


def classify(exc: BaseException) -> ErrorKind | None:
    """Map an exception to an :class:`ErrorKind`, or ``None`` for Layer 0.

    Priority follows §9: errno first (a write that failed is unambiguous),
    then typed provider codes, then transport HTTP status, then exception type.
    Anything left over is ``UNKNOWN`` — recorded, excluded from rates, never
    fatal.

    ``None`` is returned only for exception types we positively recognise as
    experiment signal, so an unrecognised failure is never silently counted as
    a packaging result.
    """
    # --- errno: a failed write is not an experiment outcome -----------------
    number = getattr(exc, "errno", None)
    if isinstance(exc, OSError) and number in _DISK_ERRNOS:
        return ErrorKind.DISK

    # --- typed provider fields ----------------------------------------------
    for attr in ("code", "type"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value in _PROVIDER_CODES:
            return _PROVIDER_CODES[value]

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        inner = body.get("error")
        if isinstance(inner, dict):
            for key in ("code", "type"):
                value = inner.get(key)
                if isinstance(value, str) and value in _PROVIDER_CODES:
                    return _PROVIDER_CODES[value]

    # --- transport status ----------------------------------------------------
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int) and status in _STATUS_KINDS:
        return _STATUS_KINDS[status]
    if isinstance(status, int) and 500 <= status < 600:
        return ErrorKind.PROVIDER_UNAVAILABLE

    # --- exception type ------------------------------------------------------
    if isinstance(exc, (subprocess.TimeoutExpired, socket.timeout, TimeoutError)):
        return ErrorKind.TIMEOUT
    if isinstance(exc, (ConnectionError, socket.gaierror)):
        return ErrorKind.NETWORK
    if isinstance(exc, OSError):
        # An OSError that reached here is a filesystem or socket failure that
        # our errno table does not name. It is still not experiment signal.
        return ErrorKind.UNKNOWN
    if isinstance(exc, MemoryError):
        return ErrorKind.UNKNOWN

    return ErrorKind.UNKNOWN


def classify_message(message: str | None) -> ErrorKind | None:
    """Best-effort classification of an *already stringified* error.

    Only for retro-classifying ledgers written before `error_kind` existed,
    where the exception object is long gone. Never used on a live run — §2
    forbids classifying from prose when the object is available.
    """
    if not message:
        return None
    text = message.lower()
    if "no space left on device" in text or "errno 28" in text:
        return ErrorKind.DISK
    if "read-only file system" in text or "errno 30" in text:
        return ErrorKind.DISK
    if "disk quota exceeded" in text or "errno 69" in text:
        return ErrorKind.DISK
    if text.startswith("oserror") or text.startswith("permissionerror"):
        return ErrorKind.DISK
    if text.startswith(("timeouterror", "timeout")):
        return ErrorKind.TIMEOUT
    if text.startswith(("connectionerror", "connectionreseterror")):
        return ErrorKind.NETWORK
    return None
