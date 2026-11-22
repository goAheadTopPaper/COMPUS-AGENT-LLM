"""Schedule branch adapter: raw timetable events -> INTEGRATION.md evidence list.

The Schedule branch hands the Supervisor a plain list, not a status dict
(INTEGRATION.md, "交付二"). Every record must carry:

    evidence_id      required, starts with ``schedule:``, stable per query
    text             required, quotable verbatim, holds course/date/time/tz/location
    citation.title   required
    course_code / start_at / location / warnings   optional structured fields

This module turns whatever the timetable source returns (eStudent, Canvas,
a local fixture) into that contract. It is deliberately a whitelist: only the
fields listed in ``_OUTPUT_FIELDS`` can reach the model, so Canvas tokens,
student IDs, emails and other personal data cannot leak into a prompt
(INTEGRATION.md:29).

IDs are derived deterministically, so re-running the same query, or asking a
different sub-query, yields the same ID for the same original event. A genuine
duplicate (same event delivered twice) collapses into one record; two distinct
events that would share a derived key receive a content-hash suffix instead of
one silently replacing the other.

Run offline tests: python3 -B -m unittest test_schedule_evidence -v
"""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

DEFAULT_TIMEZONE = "Asia/Hong_Kong"
DEFAULT_OFFSET = "+08:00"
PREFIX = "schedule:"

# Only these keys are emitted; anything else in the raw event is dropped.
_OUTPUT_FIELDS = ("course_code", "event_type", "start_at", "end_at", "location")

# Raw event aliases, in priority order. Covers eStudent/Canvas-style payloads.
_ID_KEYS = ("evidence_id", "event_id", "id", "uid", "uuid", "entry_id")
_COURSE_KEYS = ("course_code", "courseCode", "subjCode", "subject_code", "subject", "code")
_TYPE_KEYS = ("event_type", "eventType", "activity", "type", "kind", "category")
_START_KEYS = ("start_at", "starts_at", "start", "startTime", "start_time", "dtstart")
_END_KEYS = ("end_at", "ends_at", "end", "endTime", "end_time", "dtend")
_DATE_KEYS = ("date", "day", "event_date")
_TIME_KEYS = ("time", "start_time", "times")
_LOCATION_KEYS = ("location", "room", "venue", "place", "classroom")
_TZ_KEYS = ("timezone", "time_zone", "tz")

# Personal data / credentials: detected only to count them in ``stats``.
_SENSITIVE_KEY = re.compile(
    r"(?i)(token|secret|password|passwd|api[_-]?key|authorization|bearer"
    r"|cookie|session_?id|student_?id|user_?id|userid|email|phone|mobile"
    r"|student_?name|full_?name|display_?name)")
_TIME_TEXT = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _clean(value):
    """Strip control characters and collapse whitespace inside one field."""
    return re.sub(r"\s+", " ", _CONTROL.sub(" ", str(value))).strip()


def _first(row, keys):
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def _offset(text):
    """Parse ``+08:00`` / ``-05:30`` into a tzinfo."""
    match = re.match(r"^([+-])(\d{2}):?(\d{2})$", str(text).strip())
    if not match:
        raise ValueError("offset must look like +08:00")
    sign, hours, minutes = match.groups()
    delta = timedelta(hours=int(hours), minutes=int(minutes))
    return timezone(-delta if sign == "-" else delta)


def _parse_moment(value):
    """Parse an ISO-ish timestamp; returns None when unparseable."""
    text = str(value).strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_clock(value):
    """Parse ``14:00`` (or ``14:00-17:00``) into (start, end) times."""
    text = _clean(value)
    parts = [part.strip() for part in text.split("-")] if text.count("-") == 1 else [text]
    parsed = []
    for part in parts:
        match = _TIME_TEXT.match(part)
        if not match:
            return None, None
        hour, minute, second = match.groups()
        parsed.append((int(hour), int(minute), int(second or 0)))
    if len(parsed) == 2:
        return parsed[0], parsed[1]
    return parsed[0], None


def _combine(date_text, clock_text, tzinfo):
    """Combine a date and a clock string into an aware datetime."""
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", _clean(date_text))
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    start, _ = _parse_clock(clock_text) if clock_text else (None, None)
    if start is None:
        return datetime(year, month, day, tzinfo=tzinfo)
    hour, minute, second = start
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=tzinfo)
    except ValueError:  # e.g. 25:00
        return None


def _moments(row, tzinfo, warnings, stats):
    """Resolve start/end datetimes from either an ISO field or date+time fields.

    Returns ``(start, end, has_time)``. ``has_time`` is False for date-only
    events, so no midnight timestamp is invented for them.
    """
    start = end = None
    has_time = True
    raw_start, raw_end = _first(row, _START_KEYS), _first(row, _END_KEYS)
    date_value, time_value = _first(row, _DATE_KEYS), _first(row, _TIME_KEYS)
    date_only = (isinstance(raw_start, str)
                 and re.match(r"^\d{4}-\d{2}-\d{2}$", _clean(raw_start)) is not None)

    if raw_start is not None and not date_only:
        start = _parse_moment(raw_start)
        if start is None and date_value is not None:
            start = _combine(date_value, raw_start, tzinfo)
        if start is None:
            raise ValueError("unparseable start timestamp: %s" % _clean(raw_start)[:40])
    elif date_only or date_value is not None:
        start = _combine(raw_start if date_only else date_value, time_value, tzinfo)
        if start is None:
            raise ValueError("unparseable date/time: %s %s"
                             % (_clean(date_value or raw_start or "")[:20],
                                _clean(time_value or "")[:12]))
        if time_value is None:
            has_time = False
            warnings.append("Time of day is not recorded in the source for this event.")

    if not has_time:
        end = None
    elif raw_end is not None:
        end = _parse_moment(raw_end)
    elif start is not None and time_value is not None:
        _, clock_end = _parse_clock(time_value)
        if clock_end is not None:
            end = start.replace(hour=clock_end[0], minute=clock_end[1],
                                second=clock_end[2])

    if start is not None and start.tzinfo is None:
        start = start.replace(tzinfo=tzinfo)
        stats["assumed_timezone"] = stats.get("assumed_timezone", 0) + 1
        warnings.append(
            "Timezone is not stated in the source; assumed %s (%s)."
            % (stats.get("timezone") or DEFAULT_TIMEZONE, DEFAULT_OFFSET))
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=tzinfo)
    return start, end, has_time


def _text(course, event_type, start, end, has_time, tz_label, location):
    """Build the quotable sentence: label, date, time, timezone, location."""
    label = " ".join(part for part in (course, event_type) if part) or "Event"
    if start is None:
        when = "(date not recorded)"
    else:
        when = start.strftime("%Y-%m-%d")
        if has_time:
            when += " " + start.strftime("%H:%M")
            if end is not None:
                when += "-" + end.strftime("%H:%M")
    text = "%s: %s %s" % (label, when, tz_label)
    if location:
        text += "; location " + location
    return text + "."


def _record(row, settings, stats):
    """Normalise one raw event. Returns a contract record or None to skip."""
    warnings = [w for w in (row.get("warnings") or []) if isinstance(w, str) and w.strip()]
    warnings = list(settings["warnings"]) + [_clean(w) for w in warnings]
    raw_course = _first(row, _COURSE_KEYS)
    raw_type = _first(row, _TYPE_KEYS)
    raw_location = _first(row, _LOCATION_KEYS)
    course = _clean(raw_course) if raw_course is not None else None
    event_type = _clean(raw_type) if raw_type is not None else None
    location = _clean(raw_location) if raw_location is not None else None
    tz_label = _clean(_first(row, _TZ_KEYS) or settings["timezone"]) or DEFAULT_TIMEZONE

    start, end, has_time = _moments(row, settings["tzinfo"], warnings, stats)
    if start is None and location is None and not event_type:
        stats.setdefault("skipped", []).append(
            "Row without a time, location or event type: %s" % _clean(json.dumps(
                {k: row[k] for k in _COURSE_KEYS if k in row}, ensure_ascii=False))[:60])
        return None

    text = _text(course, event_type, start, end, has_time, tz_label, location)
    record = {
        "evidence_id": "",
        "text": text,
        "citation": {"title": settings["source_title"]},
    }
    if settings["source_url"]:
        record["citation"]["source_url"] = settings["source_url"]
    structured = {
        "course_code": course,
        "event_type": event_type,
        "start_at": start.isoformat() if (start is not None and has_time) else None,
        "end_at": end.isoformat() if end is not None else None,
        "location": location,
    }
    # Whitelist only: any other raw key (token, student id, email) cannot leak.
    record.update({key: structured[key] for key in _OUTPUT_FIELDS if structured[key]})
    record["warnings"] = list(dict.fromkeys(warnings))

    record["evidence_id"] = PREFIX + _key(
        row, record,
        start.strftime("%Y%m%d") if start is not None else None,
        start.strftime("%H%M") if (start is not None and has_time) else None)
    return record


def _key(row, record, when_date, when_clock):
    """Derive a stable, readable key for one original event."""
    native = _first(row, _ID_KEYS)
    if native is not None:
        key = _slug(native)
        if key:
            return key
    key = "-".join(part for part in (
        _slug(record.get("course_code") or ""),
        when_date or "nodate",
        when_clock or "notime",
        _slug(record.get("event_type") or ""),
    ) if part)
    return key or "event"


def _signature(record):
    return hashlib.sha1(json.dumps(
        {k: v for k, v in record.items() if k != "warnings"},
        sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def build_schedule_rows(events, source_title="Timetable", source_url=None,
                        timezone_name=DEFAULT_TIMEZONE, offset=DEFAULT_OFFSET,
                        warnings=(), stats=None):
    """Normalise raw events into the INTEGRATION.md evidence list.

    Args:
        events: iterable of dicts, each one actual schedule event.
        source_title: citation title shown to the user; mark synthetic data here.
        source_url: optional display URL for real data.
        timezone_name / offset: applied only when the source omits a timezone.
        warnings: source-level warnings copied into every record.
        stats: optional dict receiving ``assumed_timezone``, ``duplicates``,
            ``stripped`` and ``skipped`` counters for the Supervisor's notices.

    Returns:
        list of contract records, deduplicated by event identity.

    Raises:
        ValueError: if ``events`` is not a sequence of dicts, or a row has a
            timestamp that cannot be read. The Supervisor records that as a
            failed branch instead of answering from a fabricated time.
    """
    if isinstance(events, (str, bytes, dict)) or not hasattr(events, "__iter__"):
        raise ValueError("events must be a list of dictionaries")
    if not isinstance(source_title, str) or not source_title.strip():
        raise ValueError("source_title must be a nonempty string")
    if stats is None:
        stats = {}
    settings = {
        "source_title": _clean(source_title),
        "source_url": source_url,
        "timezone": timezone_name,
        "tzinfo": _offset(offset),
        "warnings": [_clean(w) for w in warnings if isinstance(w, str) and w.strip()],
    }
    stats.setdefault("assumed_timezone", 0)
    stats.setdefault("duplicates", 0)
    stats.setdefault("stripped", 0)
    stats.setdefault("skipped", [])
    stats["timezone"] = timezone_name

    by_key, rows = {}, []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("each schedule event must be a dictionary")
        if any(_SENSITIVE_KEY.search(str(k)) for k in event):
            stats["stripped"] = stats.get("stripped", 0) + 1
        record = _record(event, settings, stats)
        if record is None:
            continue
        key, signature = record["evidence_id"], _signature(record)
        if key in by_key:
            if by_key[key] == signature:
                stats["duplicates"] = stats.get("duplicates", 0) + 1
                continue  # same original event delivered twice
            suffix = "-" + signature[:8]
            record["evidence_id"] = key + suffix
            key = record["evidence_id"]
        by_key[key] = signature
        rows.append(record)
    return rows


def build_schedule_search(fetch, source_title="Timetable", source_url=None,
                          timezone_name=DEFAULT_TIMEZONE, offset=DEFAULT_OFFSET,
                          warnings=(), stats=None):
    """Wrap a Schedule source into a Supervisor ``schedule_search`` callable.

    Args:
        fetch: callable ``(query) -> list[dict]`` returning raw events. It may
            raise; the exception propagates so the Supervisor marks the branch
            failed and warns the user instead of pretending there was no data.
        Remaining arguments are forwarded to :func:`build_schedule_rows`.

    Returns:
        callable ``(query) -> list`` matching ``supervisor.run``'s slot.
    """
    if not callable(fetch):
        raise ValueError("fetch must be callable")

    def schedule_search(query):
        events = fetch(query)
        if events is None:
            return []
        return build_schedule_rows(
            events, source_title=source_title, source_url=source_url,
            timezone_name=timezone_name, offset=offset, warnings=warnings,
            stats=stats)

    schedule_search.__name__ = "schedule_search"
    return schedule_search
