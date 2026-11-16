"""Append-only stage timing for Superdirector work; no app or generation actions.

Examples:
  python workflow_clock.py --log task/timing.jsonl start prepare
  python workflow_clock.py --log task/timing.jsonl next upload
  python workflow_clock.py --log task/timing.jsonl stop upload
  python workflow_clock.py --log task/timing.jsonl report

Only mark real stage transitions. No historical baseline is inferred.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import sys
import time

STAGES = ("prepare", "upload", "connect", "configure", "platform_wait",
          "download_wait", "review", "audio", "archive")
WAITS = {"platform_wait", "download_wait"}
OPERATIONS = tuple(stage for stage in STAGES if stage not in WAITS)
BEIJING = timezone(timedelta(hours=8))


@contextmanager
def locked_log(path: Path):
    """A separate permanent lock avoids unlink/reopen races between processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    with lock.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + 3
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError("Timing log is busy; no event was added") from None
                time.sleep(0.025)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_events(path):
    if not path.exists():
        return []
    contents = path.read_text(encoding="utf-8")
    if contents and not contents.endswith("\n"):
        raise ValueError("Timing log has an incomplete final record; it was not changed")
    events = []
    for line, value in enumerate(contents.splitlines(), 1):
        if not value:
            raise ValueError(f"Empty record at line {line}; log was not changed")
        try:
            event = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON at line {line}; log was not changed") from None
        if not isinstance(event, dict):
            raise ValueError(f"Invalid event at line {line}")
        events.append(event)
    return events


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise ValueError("Event timestamps must be timezone-aware ISO timestamps") from None


def intervals_for(events):
    active, intervals, previous = None, [], None
    for index, event in enumerate(events, 1):
        stage, action = event.get("stage"), event.get("action")
        when = timestamp(event.get("utc"))
        if event.get("sequence") != index or stage not in STAGES:
            raise ValueError(f"Invalid event sequence or stage at line {index}")
        if previous and when < previous:
            raise ValueError("Clock moved backwards or timestamps are out of order; timing is invalid")
        previous = when
        if action == "start":
            if active:
                raise ValueError("A stage is already running; use next or stop")
            active = {"stage": stage, "start": when, "note": event.get("note")}
        elif action == "stop":
            if not active or active["stage"] != stage:
                raise ValueError("Stop must match the currently running stage")
            intervals.append({**active, "end": when, "seconds": (when-active["start"]).total_seconds()})
            active = None
        elif action == "next":
            if not active or active["stage"] == stage:
                raise ValueError("Next requires a different currently running stage")
            intervals.append({**active, "end": when, "seconds": (when-active["start"]).total_seconds()})
            active = {"stage": stage, "start": when, "note": event.get("note")}
        else:
            raise ValueError(f"Unknown event action at line {index}")
    return intervals, active


def report(events, now, required=None, baseline=None, baseline_scope=None):
    intervals, active = intervals_for(events)
    required = tuple(dict.fromkeys(required or OPERATIONS))
    if events and now < timestamp(events[-1]["utc"]):
        raise ValueError("Current clock is earlier than the last event; timing is invalid")
    totals = {stage: None for stage in STAGES}
    counts = {stage: 0 for stage in STAGES}
    for interval in intervals:
        stage = interval["stage"]
        totals[stage] = (totals[stage] or 0) + interval["seconds"]
        counts[stage] += 1
    missing = [stage for stage in required if counts[stage] == 0]
    operations_seconds = sum(totals[stage] or 0 for stage in OPERATIONS)
    waits_seconds = sum(totals[stage] or 0 for stage in WAITS)
    result = {
        "event_count": len(events),
        "stage_seconds": totals,
        "completed_intervals": counts,
        "observed_operations_seconds": operations_seconds if any(counts[s] for s in OPERATIONS) else None,
        "observed_wait_seconds": waits_seconds if any(counts[s] for s in WAITS) else None,
        "required_operation_stages": list(required),
        "unobserved_required_stages": missing,
        "unobserved_wait_stages": [s for s in STAGES if s in WAITS and not counts[s]],
        "active": None,
        "comparison": None,
        "scope_note": "Only explicitly marked, completed intervals are summed. Unobserved stages are unknown, not zero. "
                      "A stage may repeat for 480 and 1080; platform/download waits are separate. "
                      "UTC wall time is used across invocations; forward system clock changes cannot be detected.",
    }
    if active:
        result["active"] = {"stage": active["stage"], "start_utc": active["start"].isoformat(),
                            "elapsed_unfinalized_seconds": max(0, (now-active["start"]).total_seconds()),
                            "note": active.get("note")}
    if events:
        first, last = timestamp(events[0]["utc"]), timestamp(events[-1]["utc"])
        result["marked_span_seconds"] = (last-first).total_seconds()
        result["unclassified_gap_seconds"] = max(0, result["marked_span_seconds"]-operations_seconds-waits_seconds)
    if baseline is not None:
        current = sum(totals[s] or 0 for s in required)
        eligible = not active and not missing and result.get("unclassified_gap_seconds", 0) <= 0.001
        result["comparison"] = {
            "baseline_operations_seconds": baseline,
            "baseline_scope": baseline_scope,
            "selected_stages": list(required),
            "eligible": eligible,
            "blocked_reason": "Finish the active interval, observe every selected stage and resolve unclassified time gaps first" if not eligible else None,
            "current_selected_operations_seconds": current if eligible else None,
            "reduction_percent": round((1-current/baseline)*100, 2) if eligible else None,
            "target_max_seconds": baseline*0.5,
            "target_50_percent_reached": current <= baseline*0.5 if eligible else None,
            "evidence_note": "Baseline and matching scope were supplied by caller; this tool does not verify them. "
                             "Selected completed operations only; not an end-to-end generation speed claim.",
        }
    return result


def compare_logs(current, baseline, now, required=None):
    """Compare complete marked logs, including repeat counts and stage context."""
    required = tuple(dict.fromkeys(required or OPERATIONS))
    measured = report(current, now, required)
    reference = report(baseline, now, required)
    problems = []
    for label, value in (("current", measured), ("baseline", reference)):
        if value["active"] or value["unobserved_required_stages"]:
            problems.append(label + " has an active or unobserved required stage")
        if value.get("unclassified_gap_seconds", 0) > 0.001:
            problems.append(label + " has unclassified time gaps")
    def scope(events):
        from collections import Counter
        intervals, _ = intervals_for(events)
        return Counter((i["stage"], str(i.get("note") or "")) for i in intervals if i["stage"] in required)
    if scope(current) != scope(baseline):
        problems.append("selected stage counts or note contexts differ")
    base_seconds = sum(reference["stage_seconds"][s] or 0 for s in required)
    current_seconds = sum(measured["stage_seconds"][s] or 0 for s in required)
    if base_seconds <= 0:
        problems.append("baseline has no positive completed operation time")
    eligible = not problems
    measured["comparison"] = {
        "source": "baseline_log", "selected_stages": list(required),
        "eligible": eligible, "blocked_reason": "; ".join(problems) or None,
        "baseline_operations_seconds": base_seconds,
        "current_selected_operations_seconds": current_seconds if eligible else None,
        "reduction_percent": round((1-current_seconds/base_seconds)*100, 2) if eligible else None,
        "target_max_seconds": base_seconds*0.5,
        "target_50_percent_reached": current_seconds <= base_seconds*0.5 if eligible else None,
        "evidence_note": "Completed marked operations only. Matching stage counts and context do not prove "
                         "equal material complexity or review scope; verify those separately. Not a total generation speed claim.",
    }
    return measured


def positive(value):
    try:
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ValueError
        return number
    except ValueError:
        raise argparse.ArgumentTypeError("baseline must be a finite positive number") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, help="Task-specific append-only JSONL event log")
    commands = parser.add_subparsers(dest="command", required=True)
    for action in ("start", "stop", "next"):
        sub = commands.add_parser(action)
        sub.add_argument("stage", choices=STAGES)
        sub.add_argument("--note", help="Short stage context, e.g. 480 or 1080")
    commands.add_parser("status")
    sub = commands.add_parser("report")
    sub.add_argument("--required-stage", choices=OPERATIONS, action="append",
                     help="Explicit comparable operation scope; defaults to all seven operation stages")
    baseline_group = sub.add_mutually_exclusive_group()
    baseline_group.add_argument("--baseline-operations-seconds", type=positive)
    baseline_group.add_argument("--baseline-log", help="Measured earlier same-scope timing log; never inferred")
    sub.add_argument("--baseline-scope", help="Source and scope of measured baseline, required for comparison")
    args = parser.parse_args(argv)
    if args.command == "report" and args.baseline_operations_seconds is not None and not args.baseline_scope:
        parser.error("--baseline-scope is required; do not invent an earlier baseline")
    path = Path(args.log).expanduser().resolve()
    try:
        baseline_events = None
        if getattr(args, "baseline_log", None):
            baseline_path = Path(args.baseline_log).expanduser().resolve()
            if baseline_path == path or not baseline_path.is_file():
                raise ValueError("Baseline must be a different existing measured log")
            with locked_log(baseline_path):
                baseline_events = read_events(baseline_path)
        with locked_log(path):
            events = read_events(path)
            intervals_for(events)
            now = datetime.now(timezone.utc)
            if args.command in ("start", "stop", "next"):
                if args.note and len(args.note) > 500:
                    raise ValueError("note must contain at most 500 characters")
                event = {"sequence": len(events)+1, "action": args.command,
                         "stage": args.stage, "utc": now.isoformat(timespec="microseconds"),
                         "beijing": now.astimezone(BEIJING).isoformat(timespec="microseconds"),
                         "note": args.note or None}
                intervals_for([*events, event])
                # Validate before opening the log; rejected transitions append nothing.
                with path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False)+"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                events.append(event)
            output = report(events, now,
                            getattr(args, "required_stage", None),
                            getattr(args, "baseline_operations_seconds", None),
                            getattr(args, "baseline_scope", None))
            if baseline_events is not None:
                output = compare_logs(events, baseline_events, now, args.required_stage)
                output["comparison"]["baseline_log"] = str(baseline_path)
            output["log"] = str(path)
            if args.command in ("start", "stop", "next"):
                output = {key: output[key] for key in ("log", "event_count", "active", "observed_operations_seconds", "observed_wait_seconds")}
            print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error), "log": str(path)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
