"""Collect evidence from local Codex root sessions without changing source data.

Assistant reports and tool output are evidence of what was requested or executed;
this collector deliberately does not infer that a business task was completed.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Callable


def _timestamp(value, tz):
    if not value:
        return None
    try:
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return value.astimezone(tz) if value.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _text(payload):
    text = payload.get("message")
    if isinstance(text, str):
        return text
    content = payload.get("content", [])
    if isinstance(content, str):
        return content
    return "\n".join(item.get("text", "") for item in content
                     if isinstance(item, dict) and isinstance(item.get("text"), str))


def _summary(text):
    head = text.lstrip()[:1400]
    return bool(re.match(r"(?:#+\s*)?(?:Active task|Current task|Task summary|Conversation summary|Compaction summary)\b", head, re.I)
                or re.match(r"#{1,6}\s+Task and user expectations\s*(?:\n|$)", head, re.I)
                or head.startswith(("Another language model started to solve this problem",
                                    "You are now a newly spawned child agent."))
                or "This is a summary of the conversation so far" in head)


def _latest_bridge_text(text):
    """Strip injected bot context, retaining the explicit final human request."""
    markers = (
        "[End of those messages. Now reply to the user's latest message:]",
        "[Now reply to the user's latest message:]",
    )
    for marker in markers:
        if marker in text:
            return text.rsplit(marker, 1)[1].strip(), True
    # Older OpenMausBot messages append the actual request after current time.
    if text.startswith("Context from OpenMausBot updated since this conversation started;"):
        matches = list(re.finditer(r"Current time when this message was sent:[^\n]*\n", text))
        if matches:
            tail = text[matches[-1].end():].strip()
            if not tail.startswith(("[Messages this conversation received", "[Scheduled routine")):
                return tail, True
        return "[机器人注入上下文；未识别到独立人工请求]", True
    return text, False


def _user_kind(text):
    head = text.lstrip()
    if _summary(head):
        return "context_summary"
    if any(marker in head[:3000] for marker in (
            "[Scheduled routine ", "[From OpenMausBot · retry", "[From routine ",
            "OpenMausBot restarted while your previous turn here was running",
            "<heartbeat>", "<automation_id>")):
        return "automation_request"
    if "日程安排：" in head and ("每日复盘" in head or "定时" in head or "每天" in head):
        return "automation_request"
    return "user_request"


def _safe_excerpt(value, scrub, limit):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    # Redact before limiting; a credential label may precede a long value.
    value = scrub(value)
    return value if len(value) <= limit else value[:limit] + "\n[后续内容略；见来源行]"


def _thread_is_child(row):
    if row.get("agent_path"):
        return True
    source = row.get("source", "")
    if isinstance(source, str):
        try:
            decoded = json.loads(source)
        except (ValueError, TypeError):
            decoded = None
        if isinstance(decoded, dict) and "subagent" in decoded:
            return True
        return '"subagent"' in source or '"thread_spawn"' in source
    return isinstance(source, dict) and "subagent" in source


def _candidates(root, start, issues):
    db = root / "state_5.sqlite"
    if db.exists():
        try:
            con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
            try:
                con.execute("PRAGMA query_only=ON")
                con.row_factory = sqlite3.Row
                columns = {row[1] for row in con.execute("PRAGMA table_info(threads)")}
                wanted = [name for name in ("id", "title", "rollout_path", "source", "agent_path", "created_at", "updated_at") if name in columns]
                if not {"id", "rollout_path", "updated_at"}.issubset(columns):
                    raise ValueError("Unsupported threads table schema")
                # An old-created chat can still contain events in today's window.
                condition = "updated_at >= ?"
                args = [int(start.timestamp())]
                if "updated_at_ms" in columns:
                    condition += " OR updated_at_ms >= ?"
                    args.append(int(start.timestamp() * 1000))
                return [dict(row) for row in con.execute(
                    "SELECT " + ",".join(wanted) + " FROM threads WHERE " + condition, args)]
            finally:
                con.close()
        except (OSError, sqlite3.Error, ValueError) as exc:
            issues.append("Codex索引读取失败，改查会话文件：" + str(exc))
    else:
        issues.append("Codex索引不存在，按会话文件修改时间选择候选；覆盖可能不完整")
    found = []
    for directory in (root / "sessions", root / "archived_sessions"):
        if not directory.exists():
            continue
        for path in directory.rglob("*.jsonl"):
            try:
                if path.stat().st_mtime < start.timestamp():
                    continue
                with path.open(encoding="utf-8") as handle:
                    first = json.loads(handle.readline()).get("payload", {})
                found.append({"id": first.get("id", first.get("session_id", path.stem)),
                              "rollout_path": str(path), "source": first.get("source", ""),
                              "title": "", "agent_path": first.get("agent_path")})
            except (OSError, ValueError, TypeError):
                continue
    return found


def collect(codex_root: Path, start: datetime, end: datetime, scrub: Callable[[str], str]) -> dict:
    """Return redacted event evidence for a half-open aware-datetime interval.

    ``start`` determines the reporting timezone. ``tool_call`` contains names and
    call ids, never raw arguments. Tool results are scrubbed excerpts (1000 chars).
    All event ``source`` values carry the exact source path and one-based line.
    """
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("start/end must be timezone-aware and end must follow start")
    root = Path(codex_root)
    if not root.exists():
        return {"status": "unavailable", "threads": [], "events": [],
                "issues": ["Codex目录不存在"], "coverage": {"source_writes": False}}
    issues, events, threads = [], [], []
    counts = Counter()
    candidates = _candidates(root, start, issues)
    seen_paths = set()
    for row in candidates:
        if _thread_is_child(row):
            counts["subagent_threads_excluded"] += 1
            continue
        path = Path(row.get("rollout_path", ""))
        path_key = str(path).lower()
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        if not path.is_file():
            counts["missing_rollouts"] += 1
            issues.append("会话文件不可用：" + str(path))
            continue
        counts["root_threads_scanned"] += 1
        local_events, call_names = [], {}
        previous = {}
        automation_turn = False
        try:
            with path.open(encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, 1):
                    try:
                        item = json.loads(line)
                    except (ValueError, TypeError):
                        counts["malformed_lines"] += 1
                        continue
                    payload = item.get("payload", {})
                    if not isinstance(payload, dict):
                        continue
                    typ, subtyp = item.get("type"), payload.get("type")
                    stamp = _timestamp(item.get("timestamp"), start.tzinfo)
                    # Retain names from calls before midnight for results after it.
                    if typ == "response_item" and subtyp in ("function_call", "custom_tool_call"):
                        call_names[payload.get("call_id", "")] = payload.get("name", "")
                    if stamp is None or not start <= stamp < end:
                        continue
                    metadata = payload.get("internal_chat_message_metadata_passthrough", {}) or {}
                    turn_id = metadata.get("turn_id") or payload.get("turn_id") or payload.get("root_turn_id")
                    raw_text, kind, extras = "", None, {}
                    if typ == "compacted":
                        counts["context_summaries_excluded"] += 1
                        continue
                    if typ == "event_msg" and subtyp == "user_message":
                        raw_text = _text(payload)
                        kind = _user_kind(raw_text)
                        raw_text, bridge = _latest_bridge_text(raw_text)
                        extras["origin"] = "bot_bridge" if bridge else "user_event"
                    elif typ == "response_item" and subtyp == "message" and payload.get("role") == "user":
                        content_kinds = metadata.get("content_item_kinds", [])
                        if content_kinds and "user.text" not in content_kinds:
                            continue
                        raw_text = _text(payload)
                        if not content_kinds and raw_text.lstrip().startswith(("# AGENTS.md instructions", "<environment_context>", "<permissions instructions>", "<turn_aborted>")):
                            continue
                        kind = _user_kind(raw_text)
                        raw_text, bridge = _latest_bridge_text(raw_text)
                        extras["origin"] = "bot_bridge" if bridge else "user_message"
                    elif typ == "response_item" and subtyp == "message" and payload.get("role") == "assistant" and payload.get("phase") in ("final_answer", "final"):
                        raw_text = _text(payload)
                        kind = "assistant_report"
                    elif typ == "event_msg" and subtyp == "task_complete" and payload.get("last_agent_message"):
                        raw_text = payload["last_agent_message"]
                        kind = "assistant_report"
                    elif typ == "response_item" and subtyp in ("function_call", "custom_tool_call"):
                        name = payload.get("name", "unknown")
                        raw_text = "调用工具：" + name
                        extras = {"call_id": payload.get("call_id"), "tool_name": name}
                        if name in ("exec", "functions.exec"):
                            nested = payload.get("input", "") or payload.get("arguments", "")
                            if isinstance(nested, str):
                                names = sorted(set(re.findall(r"\btools\.([A-Za-z0-9_]+)\s*\(", nested)))
                                extras["nested_tool_names"] = names
                                if names:
                                    raw_text += "；内部工具：" + ", ".join(names)
                        kind = "tool_call"
                    elif typ == "response_item" and subtyp in ("function_call_output", "custom_tool_call_output"):
                        raw_text = payload.get("output", "")
                        extras = {"call_id": payload.get("call_id"), "tool_name": call_names.get(payload.get("call_id"), "unknown")}
                        kind = "tool_result"
                    if kind is None:
                        continue
                    if kind == "context_summary" or (kind == "assistant_report" and _summary(str(raw_text))):
                        counts["context_summaries_excluded"] += 1
                        continue
                    if raw_text == "[机器人注入上下文；未识别到独立人工请求]":
                        counts["bridge_contexts_excluded"] += 1
                        continue
                    if kind in ("user_request", "automation_request"):
                        # Bridge suffix itself may be an automatic request.
                        kind = _user_kind(raw_text) if kind == "user_request" else kind
                        automation_turn = kind == "automation_request"
                    if kind == "assistant_report":
                        if automation_turn or "<heartbeat>" in str(raw_text) or "<automation_id>" in str(raw_text):
                            kind = "automation_report"
                        extras["verification"] = "assistant_claim_only"
                    if kind in ("tool_call", "tool_result"):
                        extras["origin"] = "automation" if automation_turn else "agent_execution"
                    text = _safe_excerpt(raw_text, scrub, 1000 if kind == "tool_result" else 4000)
                    if not text.strip():
                        continue
                    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    group = "report" if kind in ("assistant_report", "automation_report") else kind
                    identity = (group, digest)
                    prev = previous.get(identity)
                    if prev:
                        same_turn = turn_id and turn_id == prev["turn_id"]
                        counterpart = typ != prev["record_type"] and abs((stamp - prev["timestamp"]).total_seconds()) <= 3
                        if (same_turn or counterpart) and kind not in ("tool_call", "tool_result"):
                            counts["duplicate_events_excluded"] += 1
                            continue
                    previous[identity] = {"turn_id": turn_id, "record_type": typ, "timestamp": stamp}
                    event = {"time": stamp.isoformat(), "date": stamp.date().isoformat(), "kind": kind,
                             "text": text, "thread_id": row.get("id", ""),
                             "source": {"path": str(path), "line": line_no}, **extras}
                    if turn_id:
                        event["turn_id"] = turn_id
                    local_events.append(event)
                    counts[kind] += 1
        except OSError as exc:
            issues.append("读取会话失败：" + str(path) + "：" + str(exc))
        if local_events:
            events.extend(local_events)
            threads.append({"id": row.get("id", ""), "title": scrub(row.get("title", ""))[:200],
                            "source_path": str(path), "event_count": len(local_events),
                            "first_event": local_events[0]["time"], "last_event": local_events[-1]["time"]})
    events.sort(key=lambda event: (event["time"], event["thread_id"], event["source"]["line"]))
    coverage = {"start": start.isoformat(), "end": end.isoformat(), "source_writes": False,
                "candidate_threads": len(candidates), "root_threads_with_events": len(threads),
                "events": len(events), "counts": dict(counts),
                "first_event": events[0]["time"] if events else None,
                "last_event": events[-1]["time"] if events else None,
                "assistant_reports_are_verified_completion": False,
                "tool_result_excerpt_limit": 1000}
    return {"status": "partial" if issues else ("ok" if events else "no_events"),
            "threads": threads, "events": events, "issues": [scrub(x) for x in issues], "coverage": coverage}
