"""Infra error classification, and what the ledger does with it.

The incident these exist to prevent: on 2026-08-06 `matrix-40` filled the disk
at 95% complete. 28 D1 cells were graded `fail` for running out of disk, 1380
D2/D2-auth cells were printed and dropped entirely, and `--resume` would have
preserved both mistakes forever because a row existing meant a cell was done.
"""

from __future__ import annotations

import errno
import socket
import subprocess

import pytest

from harness.engine.grader import Outcome
from harness.engine.infra import (
    FATAL,
    ErrorKind,
    classify,
    classify_message,
    error_facts,
    with_retry,
)
from harness.engine.results import ResultStore, Row, infra_row

BASE = dict(
    run_id="r1", arm="A1", task_id="t1", core_id="c1", task_class="R",
    answerable=True, repeat=0, outcome="pass", detail="", confident=False,
    clobbered=(), turns=3, calls=2, forbidden_attempts=0, truncated=False,
    error=None, error_kind=None, wall_clock_seconds=1.0, input_tokens=1000,
    cached_input_tokens=0, output_tokens=100, reasoning_tokens=0,
    static_tokens=500, per_call_overhead_tokens=0, session_setup_tokens=0,
    model="gpt-5.6-luna", mcp_spec_revision="2026-07-28", skill_condition="none",
    report_class="controlled", seed=1, surface_size=0,
)


def row(**kw) -> Row:
    return Row(**{**BASE, **kw})


# ---- classification ------------------------------------------------------

def test_enospc_is_disk() -> None:
    """The one that started all this."""
    exc = OSError(errno.ENOSPC, "No space left on device")
    assert classify(exc) is ErrorKind.DISK


def test_disk_is_fatal_so_a_full_volume_stops_the_matrix() -> None:
    assert ErrorKind.DISK in FATAL


def test_unknown_is_never_fatal() -> None:
    """§2 prefers false negatives on abort over false positives."""
    assert ErrorKind.UNKNOWN not in FATAL
    assert classify(ValueError("something odd")) is ErrorKind.UNKNOWN


def test_provider_quota_code_is_billing() -> None:
    exc = RuntimeError("spend it all")
    exc.code = "insufficient_quota"
    assert classify(exc) is ErrorKind.BILLING


def test_transport_401_is_auth() -> None:
    exc = RuntimeError("nope")
    exc.status_code = 401
    assert classify(exc) is ErrorKind.AUTH


def test_transport_429_is_rate_limit_not_fatal() -> None:
    exc = RuntimeError("slow down")
    exc.status_code = 429
    assert classify(exc) is ErrorKind.RATE_LIMIT
    assert ErrorKind.RATE_LIMIT not in FATAL


def test_timeouts_and_network_are_transient() -> None:
    assert classify(subprocess.TimeoutExpired("cmd", 1.0)) is ErrorKind.TIMEOUT
    assert classify(socket.gaierror("no dns")) is ErrorKind.NETWORK
    assert classify(ConnectionResetError()) is ErrorKind.NETWORK


# ---- the negative tests §2 asks for --------------------------------------

def test_payload_text_saying_unauthorized_is_not_auth() -> None:
    """A tool result that says "unauthorized" is the mock API doing its job.

    Classifying it as `auth` would abort a healthy matrix on a correct 401 from
    the fixture — the exact false positive the taxonomy is built to avoid.
    """
    exc = ValueError('{"error": "unauthorized: token lacks scope"}')
    assert classify(exc) is not ErrorKind.AUTH


def test_payload_text_saying_no_space_left_is_not_disk() -> None:
    exc = ValueError('tool returned: {"detail": "No space left on device"}')
    assert classify(exc) is not ErrorKind.DISK


def test_grader_failure_text_is_never_infra() -> None:
    """Layer 0 never reaches the classifier at all — grading is not an
    exception path — but a wrong answer stringified into one must not classify
    as anything fatal."""
    assert classify(AssertionError("expected 42, got 41")) not in FATAL


# ---- retro-classification of old ledgers ---------------------------------

def test_message_classifier_recovers_enospc_from_a_stringified_error() -> None:
    kind = classify_message("OSError: [Errno 28] No space left on device")
    assert kind is ErrorKind.DISK


def test_message_classifier_declines_ordinary_failures() -> None:
    assert classify_message("all assertions held") is None
    assert classify_message(None) is None


# ---- the ledger ----------------------------------------------------------

def test_infra_rows_are_not_counted_as_completed(tmp_path) -> None:
    """The bug: a row existing meant a cell was done, even when the row only
    recorded that the disk was full."""
    store = ResultStore(tmp_path)
    store.record(row(arm="D1", task_id="t1", repeat=0,
                     outcome="infra-error", error_kind="disk"))
    store.record(row(arm="D1", task_id="t2", repeat=0, outcome="pass"))

    assert store.completed() == {("D1", "t2", 0)}, "the disk row must re-run"
    assert [r["task_id"] for r in store.voided()] == ["t1"]


def test_rerunning_a_voided_cell_supersedes_it(tmp_path) -> None:
    store = ResultStore(tmp_path)
    store.record(row(arm="D1", task_id="t1", repeat=0,
                     outcome="infra-error", error_kind="disk"))
    store.record(row(arm="D1", task_id="t1", repeat=0, outcome="pass"))

    rows = list(store.rows())
    assert len(rows) == 1 and rows[0]["outcome"] == "pass"
    assert store.completed() == {("D1", "t1", 0)}
    # Append-only: the superseded row is still on disk as evidence.
    assert len(list(store.raw_rows())) == 2


def test_a_run_that_cannot_write_its_trace_still_lands_in_the_ledger(tmp_path) -> None:
    """Losing a trace costs recomputable detail. Losing the row costs the run."""
    store = ResultStore(tmp_path)

    class Unwritable:
        def write(self, directory):
            raise OSError(errno.ENOSPC, "No space left on device")

    store.record(row(arm="D1", task_id="t1", repeat=0), Unwritable())

    (written,) = list(store.raw_rows())
    assert written["outcome"] == "infra-error"
    assert written["error_kind"] == "disk"
    assert store.completed() == set(), "and it must be re-run"


def test_a_cell_lost_before_persistence_is_still_recorded(tmp_path) -> None:
    """1380 D2/D2-auth cells vanished this way — printed, never written."""
    class Task:
        id = "t1"
        core_id = "c1"
        task_class = "R"
        answerable = True

    store = ResultStore(tmp_path)
    store.record(infra_row(
        arm="D2-auth", task=Task(), repeat=0,
        exc=OSError(errno.ENOSPC, "No space left on device"),
        report_class="controlled", seed=1, model="gpt-5.6-luna", surface_size=50,
    ))

    (written,) = list(store.raw_rows())
    assert written["arm"] == "D2-auth"
    assert written["error_kind"] == "disk"
    assert written["outcome"] == str(Outcome.INFRA_ERROR)
    assert "No space left on device" in written["error"]
    assert store.completed() == set()


def test_a_pre_error_kind_ledger_is_reclassified_on_read(tmp_path) -> None:
    """matrix-40's 28 poisoned D1 rows, exactly as they sit on disk today."""
    store = ResultStore(tmp_path)
    store.record(row(
        arm="D1", task_id="core-029-W-safe", repeat=0, outcome="fail",
        detail="run error: OSError: [Errno 28] No space left on device",
        error="OSError: [Errno 28] No space left on device", error_kind=None,
    ))

    (seen,) = list(store.rows())
    assert seen["error_kind"] == "disk"
    assert seen["outcome"] == "infra-error", "must stop counting as a D1 failure"
    assert store.completed() == set(), "and --resume must re-run it"
    # The file itself is untouched.
    assert next(store.raw_rows())["outcome"] == "fail"


def test_a_genuine_failure_is_never_relabelled_as_infra(tmp_path) -> None:
    store = ResultStore(tmp_path)
    store.record(row(arm="A1", task_id="t1", outcome="fail",
                     detail="expected 42, got 41", error=None))
    (seen,) = list(store.rows())
    assert seen["outcome"] == "fail" and seen["error_kind"] is None
    assert store.completed() == {("A1", "t1", 0)}


# ---- Package C: retry ----------------------------------------------------

def test_transient_failures_are_retried_in_place() -> None:
    """A 429 at --concurrency 8 should cost 2s, not a whole resume pass."""
    attempts = []
    slept = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            exc = RuntimeError("slow down")
            exc.status_code = 429
            raise exc
        return "ok"

    assert with_retry(flaky, sleep=slept.append) == "ok"
    assert len(attempts) == 3 and len(slept) == 2


def test_fatal_failures_are_not_retried() -> None:
    """Retrying a full disk wastes time on a guaranteed identical failure."""
    attempts = []

    def dead():
        attempts.append(1)
        raise OSError(errno.ENOSPC, "No space left on device")

    with pytest.raises(OSError):
        with_retry(dead, sleep=lambda _: None)
    assert len(attempts) == 1


def test_unknown_failures_are_not_retried() -> None:
    attempts = []

    def broken():
        attempts.append(1)
        raise ValueError("bug in our own code")

    with pytest.raises(ValueError):
        with_retry(broken, sleep=lambda _: None)
    assert len(attempts) == 1


def test_exhausting_retries_reraises_for_the_normal_infra_path() -> None:
    def always():
        exc = RuntimeError("still limited")
        exc.status_code = 429
        raise exc

    with pytest.raises(RuntimeError):
        with_retry(always, attempts=3, sleep=lambda _: None)


def test_retry_after_header_is_honoured() -> None:
    slept = []

    class Resp:
        headers = {"retry-after": "7"}

    def limited():
        exc = RuntimeError("wait")
        exc.status_code = 429
        exc.response = Resp()
        raise exc

    with pytest.raises(RuntimeError):
        with_retry(limited, attempts=2, sleep=slept.append)
    assert slept == [7.0], "the server's own number, not our backoff curve"


# ---- §6 typed evidence ---------------------------------------------------

def test_error_facts_record_the_evidence_not_just_the_verdict() -> None:
    exc = RuntimeError("no credit")
    exc.status_code = 402
    exc.code = "insufficient_quota"
    facts = error_facts(exc)
    assert facts == {
        "error_kind": "billing",
        "error_http_status": 402,
        "error_provider_code": "insufficient_quota",
        "error_fatal": True,
    }


def test_error_facts_mark_transient_kinds_non_fatal() -> None:
    exc = RuntimeError("slow down")
    exc.status_code = 429
    assert error_facts(exc)["error_fatal"] is False


# ---- §7 the disk projection ----------------------------------------------
#
# The same 2026-08-06 incident from the module docstring, approached from the
# other side: the check that should have stopped the matrix before it started.

def test_projection_measures_compressed_traces(tmp_path, monkeypatch) -> None:
    import shutil

    from harness.cli import _disk_shortfall

    store = ResultStore(tmp_path)
    for i in range(5):
        (store.root / "traces" / f"r{i}.json.gz").write_bytes(b"x" * 200_000)

    # Free space is pinned rather than read from the host. The check reserves
    # 5GB of headroom, so on a developer machine sitting below that every
    # "this fits" assertion fails for a reason that has nothing to do with the
    # projection under test.
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _p: shutil._ntuple_diskusage(0, 0, 500 * 2**30))

    # 10 runs x 200KB is nothing against a volume that size, so this must fit.
    assert _disk_shortfall(store, planned=10) is None
    # ...and 100 million of them must not, or the check is not checking.
    assert _disk_shortfall(store, planned=100_000_000) is not None


def test_projection_ignores_traces_from_before_compression(tmp_path) -> None:
    """A resumed directory holds both formats. Only the new one predicts.

    Averaging in 870KB traces this run will never write again projects roughly
    4x the real need, and the failure mode is silent: the matrix refuses to
    start on a volume with room to spare, which reads exactly like a full disk.
    """
    from harness.cli import _TRACE_BYTES, _disk_shortfall

    store = ResultStore(tmp_path)
    for i in range(200):
        (store.root / "traces" / f"old{i}.json").write_bytes(b"x" * 870_000)

    # No compressed sample yet: fall back to the constant, not to the legacy
    # files sitting right there.
    huge = _disk_shortfall(store, planned=100_000_000)
    assert huge is not None
    needed, _ = huge
    assert needed == 100_000_000 * _TRACE_BYTES

    (store.root / "traces" / "new.json.gz").write_bytes(b"x" * 100_000)
    needed, _ = _disk_shortfall(store, planned=100_000_000)
    assert needed == 100_000_000 * 100_000, "legacy traces must not be sampled"


def test_smoke_skips_disk_reserve(tmp_path, monkeypatch) -> None:
    import shutil

    from harness.cli import _disk_reserve_bytes, _disk_shortfall, build_parser
    from harness.engine.results import ResultStore

    store = ResultStore(tmp_path)
    # Tighter than the 5GB default reserve, but enough for a smoke matrix.
    monkeypatch.setattr(
        shutil, "disk_usage",
        lambda _p: shutil._ntuple_diskusage(0, 0, int(1.5 * 2**30)))

    args = build_parser().parse_args(["run", "--out", str(tmp_path), "--smoke"])
    reserve = _disk_reserve_bytes(args)
    assert reserve == 0
    assert _disk_shortfall(store, planned=12, reserve_bytes=reserve) is None
    assert _disk_shortfall(store, planned=12) is not None
