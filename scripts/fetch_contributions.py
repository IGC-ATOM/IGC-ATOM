#!/usr/bin/env python3
"""Fetch a real GitHub contribution calendar and normalise it to JSON.

Reads the public, token-free endpoint that backs the calendar on a GitHub
profile page:

    https://github.com/users/<login>/contributions

Only data GitHub already exposes publicly is used. Nothing is synthesised: if
an account has no public contributions the output is an honest run of zeros.

Several logins can be merged (Parth commits from two accounts), in which case
per-day counts are summed and intensity levels are recomputed from quartiles
the way GitHub does it.

Usage:
    python fetch_contributions.py --users IGC-ATOM,parthrajpurt16
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CONTRIB_URL = "https://github.com/users/{login}/contributions"
USER_AGENT = "IGC-ATOM-profile-art/1.0 (+https://github.com/IGC-ATOM/IGC-ATOM)"
TIMEOUT = 30

# "6 contributions on August 31st." / "No contributions on August 31st."
COUNT_RE = re.compile(r"^\s*(No|[\d,]+)\s+contribution", re.IGNORECASE)
TOTAL_RE = re.compile(r"([\d,]+)\s+contributions?\s+in\s+the\s+last\s+year", re.IGNORECASE)


class FetchError(RuntimeError):
    """Raised when the calendar cannot be retrieved or parsed."""


def fetch_html(login, session):
    resp = session.get(
        CONTRIB_URL.format(login=login),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=TIMEOUT,
    )
    if resp.status_code == 404:
        raise FetchError("no such GitHub user: %s" % login)
    resp.raise_for_status()
    return resp.text


def parse_calendar(html):
    """Return ({iso_date: {count, level}}, total_reported_by_github)."""
    soup = BeautifulSoup(html, "html.parser")

    # Tooltips hold the real counts; cells hold the date and intensity level.
    tooltips = {}
    for tip in soup.find_all("tool-tip"):
        target = tip.get("for")
        if target:
            tooltips[target] = tip.get_text(strip=True)

    days = {}
    for cell in soup.select("td.ContributionCalendar-day"):
        iso = cell.get("data-date")
        if not iso:
            continue
        match = COUNT_RE.match(tooltips.get(cell.get("id", ""), ""))
        if match:
            token = match.group(1)
            count = 0 if token.lower() == "no" else int(token.replace(",", ""))
        else:
            # Cell rendered without a tooltip: record zero rather than invent one.
            count = 0
        days[iso] = {"count": count, "level": int(cell.get("data-level") or 0)}

    if not days:
        raise FetchError("contribution calendar markup not found or changed")

    heading = soup.find(id="js-contribution-activity-description")
    reported = None
    if heading:
        found = TOTAL_RE.search(" ".join(heading.get_text(" ", strip=True).split()))
        if found:
            reported = int(found.group(1).replace(",", ""))
    return days, reported


def quartile_levels(days):
    """Recompute 0-4 intensity levels from merged counts, in place."""
    active = sorted(d["count"] for d in days.values() if d["count"] > 0)
    if not active:
        for day in days.values():
            day["level"] = 0
        return

    def pct(p):
        idx = min(len(active) - 1, max(0, int(round(p * (len(active) - 1)))))
        return active[idx]

    low, mid, high = pct(0.25), pct(0.50), pct(0.75)
    for day in days.values():
        count = day["count"]
        if count <= 0:
            day["level"] = 0
        elif count <= low:
            day["level"] = 1
        elif count <= mid:
            day["level"] = 2
        elif count <= high:
            day["level"] = 3
        else:
            day["level"] = 4


def streaks(ordered, today):
    """Return (current_streak, longest_streak, longest_range)."""
    longest = run = 0
    longest_end = None
    for iso, count in ordered:
        if count > 0:
            run += 1
            if run > longest:
                longest, longest_end = run, iso
        else:
            run = 0

    # The current streak walks backwards. An empty *today* does not break it,
    # because the day is still in progress.
    current = 0
    for iso, count in reversed(ordered):
        day = date.fromisoformat(iso)
        if day > today:
            continue
        if count > 0:
            current += 1
        elif day == today:
            continue
        else:
            break

    longest_range = None
    if longest_end:
        end = date.fromisoformat(longest_end)
        longest_range = {
            "start": (end - timedelta(days=longest - 1)).isoformat(),
            "end": longest_end,
        }
    return current, longest, longest_range


def build_payload(days, logins, reported):
    ordered_dates = sorted(days)
    ordered = [(iso, days[iso]["count"]) for iso in ordered_dates]
    today = datetime.now(timezone.utc).date()

    total = sum(count for _, count in ordered)
    active_days = sum(1 for _, count in ordered if count > 0)
    current, longest, longest_range = streaks(ordered, today)
    best_iso, best_count = max(ordered, key=lambda kv: (kv[1], kv[0]))

    monthly = OrderedDict()
    for iso, count in ordered:
        monthly[iso[:7]] = monthly.get(iso[:7], 0) + count

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": "https://github.com/users/<login>/contributions",
        "accounts": logins,
        "range": {"start": ordered_dates[0], "end": ordered_dates[-1]},
        "stats": {
            "total": total,
            "reported_total": reported,
            "active_days": active_days,
            "tracked_days": len(ordered),
            "current_streak": current,
            "longest_streak": longest,
            "longest_streak_range": longest_range,
            "best_day": {"date": best_iso, "count": best_count} if best_count else None,
            "max_daily": best_count,
            "monthly": dict(monthly),
        },
        "days": [
            {"date": iso, "count": days[iso]["count"], "level": days[iso]["level"]}
            for iso in ordered_dates
        ],
    }


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Fetch GitHub contribution data.")
    parser.add_argument("--users", default="IGC-ATOM",
                        help="comma-separated GitHub logins to merge")
    parser.add_argument("--out", default=str(root / "data" / "contributions.json"))
    args = parser.parse_args()

    logins = [u.strip() for u in args.users.split(",") if u.strip()]
    if not logins:
        print("error: no logins given", file=sys.stderr)
        return 2

    merged = {}
    reported_total = 0
    session = requests.Session()

    for login in logins:
        try:
            days, reported = parse_calendar(fetch_html(login, session))
        except (FetchError, requests.RequestException) as exc:
            print("error: %s: %s" % (login, exc), file=sys.stderr)
            return 1
        if reported is not None:
            reported_total += reported
        print("  %s: %d days, %d contributions"
              % (login, len(days), sum(d["count"] for d in days.values())))
        for iso, day in days.items():
            slot = merged.setdefault(iso, {"count": 0, "level": 0})
            slot["count"] += day["count"]
            slot["level"] = max(slot["level"], day["level"])

    if len(logins) > 1:
        quartile_levels(merged)

    payload = build_payload(merged, logins, reported_total or None)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    stats = payload["stats"]
    print("wrote %s" % out)
    print("  total=%d active_days=%d current_streak=%d longest_streak=%d"
          % (stats["total"], stats["active_days"],
             stats["current_streak"], stats["longest_streak"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
