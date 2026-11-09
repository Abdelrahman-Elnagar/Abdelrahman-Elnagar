"""Collect the numbers the profile card and the Pac-Man board are drawn from.

Writes:
    cache/stats.json     repos, contributed repos, stars, commits, followers, lines of code
    cache/calendar.json  the contribution calendar (weeks x 7 days, with levels)
    cache/loc.json       per-repo line counts, reused until a repo's head moves

Only public endpoints are needed, so it runs the same on a laptop and in
Actions. Set GITHUB_TOKEN to lift the rate limit, and STATS_TOKEN (a PAT with
`repo` scope) to also count private repositories.

Usage:
    python tools/fetch_stats.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from theme import LOGIN, ROOT

CACHE = ROOT / "cache"
API = "https://api.github.com"
TOOLTIP = re.compile(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>')
CELL_ID = re.compile(r'<td[^>]*?data-date="([\d-]+)"[^>]*?id="([^"]+)"[^>]*?data-level="(\d)"[^>]*?>')

TOKEN = os.environ.get("STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
PRIVATE = bool(os.environ.get("STATS_TOKEN"))


class RateLimited(RuntimeError):
    pass


def request(url: str, accept: str = "application/vnd.github+json") -> tuple[int, object, dict]:
    headers = {"Accept": accept, "User-Agent": f"{LOGIN}-profile-card"}
    if TOKEN and url.startswith(API):
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body and "json" in resp.headers.get("Content-Type", "") else body
            return resp.status, data, dict(resp.headers)
    except urllib.error.HTTPError as err:
        if err.code in (403, 429):
            raise RateLimited(f"rate limited on {url} ({err.code}); set GITHUB_TOKEN to lift the limit") from err
        raise


def get(url: str):
    return request(url if url.startswith("http") else API + url)[1]


def paged(url: str) -> list:
    out, page = [], 1
    while True:
        chunk = get(f"{url}{'&' if '?' in url else '?'}per_page=100&page={page}")
        out += chunk
        if len(chunk) < 100:
            return out
        page += 1


# --- Repos ------------------------------------------------------------------
def owned_repos() -> list[dict]:
    if PRIVATE:
        repos = paged("/user/repos?affiliation=owner")
    else:
        repos = paged(f"/users/{LOGIN}/repos?type=owner")
    return [r for r in repos if not r["fork"] and r["owner"]["login"].lower() == LOGIN.lower()]


def contributed_repos() -> int:
    """Other people's repositories this account has opened a pull request against."""
    data = get(f"/search/issues?q=author:{LOGIN}+type:pr+-user:{LOGIN}&per_page=100")
    return len({item["repository_url"] for item in data["items"]})


def commit_total() -> int:
    status, data, _ = request(f"{API}/search/commits?q=author:{LOGIN}&per_page=1")
    return int(data["total_count"])


# --- Lines of code ----------------------------------------------------------
def repo_lines(full_name: str) -> tuple[int, int]:
    """Lines added and deleted by this account in one repo (GitHub's contributor stats)."""
    for _ in range(8):
        status, data, _ = request(f"{API}/repos/{full_name}/stats/contributors")
        if status == 200 and isinstance(data, list):
            for entry in data:
                if (entry.get("author") or {}).get("login", "").lower() == LOGIN.lower():
                    return (sum(w["a"] for w in entry["weeks"]), sum(w["d"] for w in entry["weeks"]))
            return 0, 0
        if status == 204:
            return 0, 0
        time.sleep(3)  # 202: GitHub is still computing the stats
    return 0, 0


def lines_of_code(repos: list[dict]) -> tuple[int, int]:
    cache_path = CACHE / "loc.json"
    cache = json.loads(cache_path.read_text("utf-8")) if cache_path.exists() else {}
    fresh, added, deleted = {}, 0, 0
    limited = False
    for repo in repos:
        name, pushed = repo["full_name"], repo["pushed_at"]
        hit = cache.get(name)
        if hit and hit["pushed"] == pushed:
            entry = hit
        elif limited:
            entry = hit or {"pushed": "", "add": 0, "del": 0}  # stale beats missing
        else:
            try:
                a, d = repo_lines(name)
                entry = {"pushed": pushed, "add": a, "del": d}
                print(f"  loc {name}: +{a:,} -{d:,}")
            except RateLimited as err:
                print(f"  {err}; keeping cached line counts for the rest")
                limited = True
                entry = hit or {"pushed": "", "add": 0, "del": 0}
        fresh[name] = entry
        added += entry["add"]
        deleted += entry["del"]
        cache_path.write_text(json.dumps(fresh, indent=1), "utf-8")  # survive a crash
    return added, deleted


# --- Calendar ---------------------------------------------------------------
def fetch_calendar() -> dict:
    """Scrape the public contribution graph into weeks x 7 days (Sunday first)."""
    html = request(f"https://github.com/users/{LOGIN}/contributions", "text/html")[1]
    text = {cid: msg for cid, msg in TOOLTIP.findall(html)}
    days = {}
    for date, cid, level in CELL_ID.findall(html):
        m = re.match(r"(\d+) contribution", text.get(cid, "").strip())
        days[dt.date.fromisoformat(date)] = (int(m.group(1)) if m else 0, int(level))
    if not days:
        raise SystemExit("could not read the contribution calendar")

    first = min(days)
    start = first - dt.timedelta(days=(first.weekday() + 1) % 7)  # back to that week's Sunday
    last = max(days)
    weeks = []
    cursor = start
    while cursor <= last:
        week = []
        for i in range(7):
            day = cursor + dt.timedelta(days=i)
            if day in days:
                count, level = days[day]
                week.append({"date": day.isoformat(), "count": count, "level": level})
            else:
                week.append(None)
        weeks.append(week)
        cursor += dt.timedelta(days=7)
    return {"total": sum(c for c, _ in days.values()), "weeks": weeks}


def main() -> None:
    CACHE.mkdir(exist_ok=True)
    previous = {}
    if (CACHE / "stats.json").exists():
        previous = json.loads((CACHE / "stats.json").read_text("utf-8"))

    def safe(key, fn):
        try:
            return fn()
        except RateLimited as err:
            print(f"  {key}: {err}; keeping the previous value")
            return previous.get(key, 0)

    user = get(f"/users/{LOGIN}")
    repos = owned_repos()
    print(f"repos    : {len(repos)} owned, {sum(r['stargazers_count'] for r in repos)} stars")

    added, deleted = lines_of_code(repos)
    stats = {
        "repos": len(repos),
        "contrib": safe("contrib", contributed_repos),
        "stars": sum(r["stargazers_count"] for r in repos),
        "commits": safe("commits", commit_total),
        "followers": user["followers"],
        "loc": added - deleted,
        "added": added,
        "deleted": deleted,
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    (CACHE / "stats.json").write_text(json.dumps(stats, indent=1), "utf-8")
    print("stats    :", {k: v for k, v in stats.items() if k != "updated"})

    cal = fetch_calendar()
    (CACHE / "calendar.json").write_text(json.dumps(cal), "utf-8")
    print(f"calendar : {len(cal['weeks'])} weeks, {cal['total']} contributions")


if __name__ == "__main__":
    main()
