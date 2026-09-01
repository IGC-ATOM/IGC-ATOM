#!/usr/bin/env python3
"""Collect verified GitHub activity and normalise it to JSON.

Three independent sources, all real; none of them invents anything:

  public   The token-free calendar behind a profile page,
           https://github.com/users/<login>/contributions
           Counts exactly what GitHub publishes. Works in CI with no token.

  commits  An authenticated scan of the repositories the account owns:
           every commit authored by one of the given logins, deduplicated by
           SHA, bucketed by its real author date. Needs a token with `repo`.
           This sees work that lives in private repositories, which the public
           calendar withholds until "Include private contributions on my
           profile" is switched on.

  pulls    Pull requests opened by the logins, via the search API. GitHub
           counts an opened PR as a contribution in its own right, and the
           commit scan cannot see them. Needs a token.

`commits` and `pulls` measure disjoint event types and are summed; `public` is
GitHub's own count of that same underlying activity, so it is compared against
the sum rather than added to it.

Each source is stored separately under "sources" and a run only refreshes the
sources it was asked for, so a tokenless CI run can never erase commit data
gathered locally. The rendered day series is the strongest verified evidence
of activity on each date.

Dates and counts are reproduced exactly as observed. Only the 0-5 intensity
level is derived, and only for colouring.

Usage:
    python fetch_contributions.py                       # public only (CI)
    python fetch_contributions.py --sources public,commits,pulls
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CONTRIB_URL = "https://github.com/users/{login}/contributions"
API = "https://api.github.com"
USER_AGENT = "IGC-ATOM-profile-art/1.0 (+https://github.com/IGC-ATOM/IGC-ATOM)"
TIMEOUT = 30
WINDOW_DAYS = 366

COUNT_RE = re.compile(r"^\s*(No|[\d,]+)\s+contribution", re.IGNORECASE)

# Highest level index used for colouring (0 = empty).
MAX_LEVEL = 5

# Sources measuring disjoint event types are summed into one reconstruction;
# "public" is GitHub's own published count of the same underlying activity, so
# it is compared against that reconstruction rather than added to it.
ADDITIVE_SOURCES = ("commits", "pulls")


class FetchError(RuntimeError):
    """Raised when a source cannot be retrieved or parsed."""


# --------------------------------------------------------------------------
# source: public contribution calendar (no token)
# --------------------------------------------------------------------------

def fetch_public(logins, session):
    """Return {iso_date: count} summed over the given logins."""
    days = {}
    for login in logins:
        resp = session.get(CONTRIB_URL.format(login=login),
                           headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                           timeout=TIMEOUT)
        if resp.status_code == 404:
            raise FetchError("no such GitHub user: %s" % login)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        tips = {t.get("for"): t.get_text(strip=True)
                for t in soup.find_all("tool-tip") if t.get("for")}

        found = 0
        for cell in soup.select("td.ContributionCalendar-day"):
            iso = cell.get("data-date")
            if not iso:
                continue
            found += 1
            match = COUNT_RE.match(tips.get(cell.get("id", ""), ""))
            token = match.group(1) if match else "No"
            count = 0 if token.lower() == "no" else int(token.replace(",", ""))
            if count:
                days[iso] = days.get(iso, 0) + count
        if not found:
            raise FetchError("calendar markup not found or changed for %s" % login)
        print("    public/%s: %d contributions" % (login, sum(days.values())))
    return days


# --------------------------------------------------------------------------
# source: authenticated commit scan
# --------------------------------------------------------------------------

def resolve_token():
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True,
                             text=True, timeout=20)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def api_get(session, path, token, params=None):
    resp = session.get(API + path, timeout=TIMEOUT, params=params,
                       headers={"User-Agent": USER_AGENT,
                                "Accept": "application/vnd.github+json",
                                "Authorization": "Bearer " + token})
    if resp.status_code in (403, 404, 409):
        return None
    resp.raise_for_status()
    return resp.json()


def fetch_pulls(logins, session, token, since):
    """Return {iso_date: count} of pull requests opened by *logins*.

    GitHub counts an opened PR as a contribution in its own right, so this is a
    real event type that the commit scan does not see.
    """
    days = {}
    for login in logins:
        query = "author:%s type:pr created:>=%s" % (login, since[:10])
        page = 1
        while True:
            found = api_get(session, "/search/issues", token,
                            {"q": query, "per_page": 100, "page": page})
            if not found or not found.get("items"):
                break
            for item in found["items"]:
                days[item["created_at"][:10]] = days.get(item["created_at"][:10], 0) + 1
            if len(found["items"]) < 100:
                break
            page += 1
    print("    pulls: %d pull requests over %d days" % (sum(days.values()), len(days)))
    return days


def fetch_commits(logins, session, token, since):
    """Return {iso_date: count} of commits authored by *logins*.

    Deduplicated by SHA across every branch, so a commit that appears on both
    a feature branch and the default branch is counted once.
    """
    wanted = {login.lower() for login in logins}
    repos = api_get(session, "/user/repos", token,
                    {"per_page": 100, "affiliation": "owner"})
    if repos is None:
        raise FetchError("token cannot list repositories (needs `repo` scope)")

    seen = set()
    days = {}
    for repo in repos:
        full = repo["full_name"]
        branches = api_get(session, "/repos/%s/branches" % full, token,
                           {"per_page": 100}) or []
        for branch in branches:
            page = 1
            while True:
                commits = api_get(session, "/repos/%s/commits" % full, token,
                                  {"sha": branch["name"], "since": since,
                                   "per_page": 100, "page": page})
                if not commits:
                    break
                for commit in commits:
                    sha = commit.get("sha")
                    if not sha or sha in seen:
                        continue
                    seen.add(sha)
                    author = commit.get("author") or {}
                    if (author.get("login") or "").lower() not in wanted:
                        continue
                    iso = commit["commit"]["author"]["date"][:10]
                    days[iso] = days.get(iso, 0) + 1
                if len(commits) < 100:
                    break
                page += 1
    print("    commits: %d commits over %d days (%d repos scanned)"
          % (sum(days.values()), len(days), len(repos)))
    return days


# --------------------------------------------------------------------------
# levels, stats, assembly
# --------------------------------------------------------------------------

def assign_levels(days):
    """Map real counts onto 0..MAX_LEVEL, in place.

    Thresholds come from the data itself: the distinct non-zero counts are
    ranked and spread across the available levels, so the quietest real day is
    always visibly above empty and the busiest always reaches the top. Ranking
    distinct values (rather than quantiles over days) keeps the scale readable
    when one count dominates -- six days of a single commit must not swallow
    four of the five levels.
    """
    distinct = sorted({d["count"] for d in days.values() if d["count"] > 0})
    if not distinct:
        for day in days.values():
            day["level"] = 0
        return {}

    span = max(1, len(distinct) - 1)
    level_of = {}
    for i, value in enumerate(distinct):
        level_of[value] = 1 + int(round(i * (MAX_LEVEL - 1) / float(span)))
    for day in days.values():
        day["level"] = level_of.get(day["count"], 0) if day["count"] > 0 else 0
    return level_of


def streaks(ordered, today):
    longest = run = 0
    longest_end = None
    for iso, count in ordered:
        if count > 0:
            run += 1
            if run > longest:
                longest, longest_end = run, iso
        else:
            run = 0

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

    span = None
    if longest_end:
        end = date.fromisoformat(longest_end)
        span = {"start": (end - timedelta(days=longest - 1)).isoformat(),
                "end": longest_end}
    return current, longest, span


def build_payload(sources, logins, window_start, window_end):
    """Merge sources (per-date maximum) and derive stats."""
    merged = {}
    cursor = window_start
    while cursor <= window_end:
        merged[cursor.isoformat()] = {"count": 0, "level": 0}
        cursor += timedelta(days=1)

    reconstructed = {}
    for name, payload in sources.items():
        if name in ADDITIVE_SOURCES:
            for iso, count in payload["days"].items():
                reconstructed[iso] = reconstructed.get(iso, 0) + int(count)
    for name, payload in sources.items():
        if name in ADDITIVE_SOURCES:
            continue
        for iso, count in payload["days"].items():
            reconstructed[iso] = max(reconstructed.get(iso, 0), int(count))
    for iso, count in reconstructed.items():
        if iso in merged:
            merged[iso]["count"] = count

    level_of = assign_levels(merged)

    ordered_dates = sorted(merged)
    ordered = [(iso, merged[iso]["count"]) for iso in ordered_dates]
    total = sum(c for _, c in ordered)
    active = sum(1 for _, c in ordered if c > 0)
    current, longest, span = streaks(ordered, datetime.now(timezone.utc).date())
    best_iso, best_count = max(ordered, key=lambda kv: (kv[1], kv[0]))

    monthly = OrderedDict()
    for iso, count in ordered:
        monthly[iso[:7]] = monthly.get(iso[:7], 0) + count

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "accounts": logins,
        "range": {"start": ordered_dates[0], "end": ordered_dates[-1]},
        "sources": sources,
        "stats": {
            "total": total,
            "active_days": active,
            "tracked_days": len(ordered),
            "current_streak": current,
            "longest_streak": longest,
            "longest_streak_range": span,
            "best_day": {"date": best_iso, "count": best_count} if best_count else None,
            "max_daily": best_count,
            "level_thresholds": {str(k): v for k, v in sorted(level_of.items())},
            "monthly": dict(monthly),
        },
        "days": [{"date": iso, "count": merged[iso]["count"], "level": merged[iso]["level"]}
                 for iso in ordered_dates],
    }


def stable_stamp(payload, out):
    """Reuse the previous timestamp when nothing else moved."""
    if not out.exists():
        return payload
    try:
        previous = json.loads(out.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return payload
    for key in ("generated_at",):
        candidate = dict(payload, **{key: previous.get(key)})
        for name, src in candidate.get("sources", {}).items():
            old = previous.get("sources", {}).get(name, {})
            if src.get("days") == old.get("days"):
                src["updated_at"] = old.get("updated_at", src.get("updated_at"))
        if candidate == previous:
            return candidate
    return payload


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Collect verified GitHub activity.")
    parser.add_argument("--users", default="IGC-ATOM",
                        help="comma-separated GitHub logins")
    parser.add_argument("--sources", default="public",
                        help="comma-separated: public, commits, pulls")
    parser.add_argument("--out", default=str(root / "data" / "contributions.json"))
    args = parser.parse_args()

    logins = [u.strip() for u in args.users.split(",") if u.strip()]
    wanted = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    if not logins or not wanted:
        print("error: --users and --sources must be non-empty", file=sys.stderr)
        return 2

    out = Path(args.out)
    existing = {}
    if out.exists():
        try:
            existing = json.loads(out.read_text(encoding="utf-8")).get("sources", {}) or {}
        except (ValueError, OSError):
            existing = {}

    window_end = datetime.now(timezone.utc).date()
    window_start = window_end - timedelta(days=WINDOW_DAYS - 1)
    since = datetime(window_start.year, window_start.month, window_start.day,
                     tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

    sources = dict(existing)
    session = requests.Session()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    for name in wanted:
        print("  source: %s" % name)
        try:
            if name == "public":
                days = fetch_public(logins, session)
            elif name in ("commits", "pulls"):
                token = resolve_token()
                if not token:
                    raise FetchError("no token (set GITHUB_TOKEN or run `gh auth login`)")
                days = (fetch_commits(logins, session, token, since) if name == "commits"
                        else fetch_pulls(logins, session, token, since))
            else:
                raise FetchError("unknown source")
        except (FetchError, requests.RequestException) as exc:
            # Keep whatever this source contributed previously rather than
            # dropping verified activity because one run failed.
            print("    skipped: %s" % exc, file=sys.stderr)
            continue
        sources[name] = {"updated_at": now, "total": sum(days.values()),
                         "active_days": len(days), "days": days}

    if not sources:
        print("error: no source produced data", file=sys.stderr)
        return 1

    payload = build_payload(sources, logins, window_start, window_end)
    payload = stable_stamp(payload, out)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    stats = payload["stats"]
    print("wrote %s" % out)
    print("  sources=%s total=%d active_days=%d max_daily=%d levels=%s"
          % (",".join(sorted(sources)), stats["total"], stats["active_days"],
             stats["max_daily"], stats["level_thresholds"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
