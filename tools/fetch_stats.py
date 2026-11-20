"""Fetch GitHub statistics into `cache/`: `stats.json` for the card, `calendar.json`
for the Pac-Man board.

Split from `tools/build_card.py` because this half is network-bound and
rate-limited, so it memoises per-repo history walks in `cache/loc.json` keyed
by each default branch head OID.

Requires a `GITHUB_TOKEN` in the environment (the Actions-provided token covers
all public repositories and contributions).

Usage:
    GITHUB_TOKEN=... python tools/fetch_stats.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache"
STATS_OUT = CACHE_DIR / "stats.json"
LOC_CACHE = CACHE_DIR / "loc.json"
CALENDAR_OUT = CACHE_DIR / "calendar.json"

LOGIN = os.environ.get("GH_LOGIN", "manhtuan28")
ENDPOINT = "https://api.github.com/graphql"
TOKEN = os.environ.get("GITHUB_TOKEN")

SESSION = requests.Session()

LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

REPOS_QUERY = """
query($login:String!, $after:String) {
  user(login:$login) {
    id
    createdAt
    followers { totalCount }
    repositories(ownerAffiliations:OWNER, isFork:false, first:100, after:$after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        stargazerCount
        defaultBranchRef { target { ... on Commit { oid } } }
      }
    }
  }
}
"""

CALENDAR_QUERY = """
query($login:String!) {
  user(login:$login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date weekday contributionCount contributionLevel }
        }
      }
    }
  }
}
"""

CONTRIB_QUERY = """
query($login:String!) {
  user(login:$login) {
    repositoriesContributedTo(
      first:1,
      contributionTypes:[COMMIT, PULL_REQUEST, REPOSITORY]
    ) { totalCount }
  }
}
"""

COMMITS_QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""

HISTORY_QUERY = """
query($owner:String!, $name:String!, $authorId:ID!, $after:String) {
  repository(owner:$owner, name:$name) {
    defaultBranchRef {
      target { ... on Commit {
        history(first:100, after:$after, author:{id:$authorId}) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes { additions deletions }
        }
      }}
    }
  }
}
"""


def run_graphql(document: str, variables: dict, attempt: int = 0) -> dict:
    """POST a GraphQL `document`, retrying up to 3 times on secondary rate limits."""
    http_response = SESSION.post(
        ENDPOINT,
        json={"query": document, "variables": variables},
        headers={"Authorization": f"bearer {TOKEN}"},
        timeout=30,
    )
    if http_response.status_code in (403, 429) and attempt < 3:
        wait_seconds = int(http_response.headers.get("Retry-After", 60))
        print(f"  rate limited, sleeping {wait_seconds}s", file=sys.stderr)
        time.sleep(wait_seconds)
        return run_graphql(document, variables, attempt + 1)

    http_response.raise_for_status()
    payload = http_response.json()
    if "errors" in payload:
        raise SystemExit(f"GraphQL error: {json.dumps(payload['errors'], indent=2)}")
    return payload["data"]


def fetch_repos() -> tuple[dict, list[dict]]:
    """Return `(user_meta, repos)` paginating through every owned non-fork repository."""
    repos: list[dict] = []
    user_meta: dict = {}
    cursor = None
    while True:
        user_data = run_graphql(REPOS_QUERY, {"login": LOGIN, "after": cursor})["user"]
        if not user_meta:
            user_meta = {
                "id": user_data["id"],
                "createdAt": user_data["createdAt"],
                "followers": user_data["followers"]["totalCount"],
                "repos": user_data["repositories"]["totalCount"],
            }
        repos.extend(user_data["repositories"]["nodes"])
        page_info = user_data["repositories"]["pageInfo"]
        if not page_info["hasNextPage"]:
            return user_meta, repos
        cursor = page_info["endCursor"]


def fetch_commit_total(created_at: str) -> int:
    """Sum commit contributions year by year from `created_at` until now."""
    start_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now_utc = datetime.now(timezone.utc)
    total_commits = 0
    cursor_date = start_date
    while cursor_date < now_utc:
        try:
            next_year = cursor_date.replace(year=cursor_date.year + 1)
        except ValueError:
            next_year = cursor_date.replace(year=cursor_date.year + 1, day=28)
        end_date = min(next_year, now_utc)
        contrib_data = run_graphql(
            COMMITS_QUERY,
            {
                "login": LOGIN,
                "from": cursor_date.isoformat().replace("+00:00", "Z"),
                "to": end_date.isoformat().replace("+00:00", "Z"),
            },
        )["user"]["contributionsCollection"]
        total_commits += contrib_data["totalCommitContributions"] + contrib_data["restrictedContributionsCount"]
        cursor_date = end_date
    return total_commits


def fetch_loc(repos: list[dict], author_id: str) -> tuple[int, int]:
    """Sum additions and deletions authored across `repos`, memoised by head OID."""
    cache = json.loads(LOC_CACHE.read_text(encoding="utf-8")) if LOC_CACHE.exists() else {}
    total_added = 0
    total_deleted = 0
    walked_count = 0
    reused_count = 0

    for repo in repos:
        full_name = repo["nameWithOwner"]
        target = (repo.get("defaultBranchRef") or {}).get("target") or {}
        head_oid = target.get("oid")
        if not head_oid:
            continue

        cached_entry = cache.get(full_name)
        if cached_entry and cached_entry.get("oid") == head_oid:
            total_added += cached_entry["added"]
            total_deleted += cached_entry["deleted"]
            reused_count += 1
            continue

        owner, repo_name = full_name.split("/", 1)
        repo_added = 0
        repo_deleted = 0
        cursor = None
        while True:
            branch_target = run_graphql(
                HISTORY_QUERY,
                {
                    "owner": owner,
                    "name": repo_name,
                    "authorId": author_id,
                    "after": cursor,
                },
            )["repository"]["defaultBranchRef"]["target"]
            history = branch_target["history"]
            for commit_node in history["nodes"]:
                repo_added += commit_node["additions"]
                repo_deleted += commit_node["deletions"]
            if not history["pageInfo"]["hasNextPage"]:
                break
            cursor = history["pageInfo"]["endCursor"]

        cache[full_name] = {"oid": head_oid, "added": repo_added, "deleted": repo_deleted}
        total_added += repo_added
        total_deleted += repo_deleted
        walked_count += 1
        print(f"  walked {full_name}: +{repo_added:,} -{repo_deleted:,}")

    CACHE_DIR.mkdir(exist_ok=True)
    LOC_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    print(f"  loc cache: {walked_count} walked, {reused_count} reused")
    return total_added, total_deleted


def fetch_calendar() -> dict:
    """Fetch weekly contribution slots (`0 = Sunday`), padding missing days with `None`."""
    calendar = run_graphql(CALENDAR_QUERY, {"login": LOGIN})["user"]["contributionsCollection"][
        "contributionCalendar"
    ]
    weeks = []
    for week in calendar["weeks"]:
        slots: list[dict | None] = [None] * 7
        for day in week["contributionDays"]:
            slots[day["weekday"]] = {
                "date": day["date"],
                "count": day["contributionCount"],
                "level": LEVELS[day["contributionLevel"]],
            }
        weeks.append(slots)
    return {"total": calendar["totalContributions"], "weeks": weeks}


def main() -> None:
    """Entrypoint to fetch GitHub profile stats and contribution calendar into `cache/`."""
    if not TOKEN:
        raise SystemExit("GITHUB_TOKEN is not set")

    print(f"fetching stats for {LOGIN}")
    user_meta, repos = fetch_repos()
    print(f"  repos: {user_meta['repos']} | followers: {user_meta['followers']}")

    total_stars = sum(repo["stargazerCount"] for repo in repos)
    contrib_count = run_graphql(CONTRIB_QUERY, {"login": LOGIN})["user"]["repositoriesContributedTo"][
        "totalCount"
    ]
    commit_count = fetch_commit_total(user_meta["createdAt"])
    added_lines, deleted_lines = fetch_loc(repos, user_meta["id"])

    stats_payload = {
        "repos": user_meta["repos"],
        "contrib": contrib_count,
        "stars": total_stars,
        "commits": commit_count,
        "followers": user_meta["followers"],
        "loc": added_lines - deleted_lines,
        "added": added_lines,
        "deleted": deleted_lines,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    CACHE_DIR.mkdir(exist_ok=True)
    STATS_OUT.write_text(json.dumps(stats_payload, indent=2), encoding="utf-8")
    print(json.dumps(stats_payload, indent=2))

    calendar_payload = fetch_calendar()
    CALENDAR_OUT.write_text(json.dumps(calendar_payload, indent=1), encoding="utf-8")
    print(f"  calendar: {len(calendar_payload['weeks'])} weeks, {calendar_payload['total']} contributions")


if __name__ == "__main__":
    main()
