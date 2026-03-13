import logging
from collections import defaultdict
from datetime import datetime, timedelta

import requests

from app.shared.config.app_config import app_config

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_ORG = "ministryofjustice"
GITHUB_REPO = "modernisation-platform"
GITHUB_TEAM_SLUG = "modernisation-platform-engineers"

EXCLUDED_TEAM_MEMBERS = frozenset(
    ["dms1981", "davidkelliott", "modernisation-platform-ci"]
)

_team_members_cache: dict = {"members": [], "timestamp": None}


def _get_github_headers() -> dict | None:
    token = app_config.github.token
    if not token:
        logger.warning("ADMIN_GITHUB_TOKEN not configured")
        return None
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def get_team_members() -> list[str]:
    """Return active team members, excluding known departed members. Cached for 1 hour."""
    global _team_members_cache

    if _team_members_cache["timestamp"]:
        age = (datetime.utcnow() - _team_members_cache["timestamp"]).total_seconds()
        if age < 3600:
            return _team_members_cache["members"]

    headers = _get_github_headers()
    if not headers:
        return []

    try:
        response = requests.get(
            f"{GITHUB_API_BASE}/orgs/{GITHUB_ORG}/teams/{GITHUB_TEAM_SLUG}/members",
            headers=headers,
            params={"per_page": 100},
            timeout=10,
        )
        if response.status_code == 200:
            all_members = [m["login"] for m in response.json()]
            members = [m for m in all_members if m not in EXCLUDED_TEAM_MEMBERS]
            _team_members_cache = {"members": members, "timestamp": datetime.utcnow()}
            logger.info(f"Fetched {len(members)} active team members")
            return members

        logger.error(f"Failed to fetch team members: {response.status_code}")
        return []
    except Exception as e:
        logger.error(f"Error fetching team members: {e}")
        return []


def get_github_issue_count(label: str | None = None) -> int:
    """Return the count of open issues, optionally filtered by label."""
    headers = _get_github_headers()
    if not headers:
        return 0

    try:
        params: dict = {"state": "open", "per_page": 100}
        if label:
            params["labels"] = label

        response = requests.get(
            f"{GITHUB_API_BASE}/repos/{GITHUB_ORG}/{GITHUB_REPO}/issues",
            headers=headers,
            params=params,
            timeout=10,
        )
        if response.status_code == 200:
            # The GitHub issues API also returns pull requests; exclude them
            return len([i for i in response.json() if "pull_request" not in i])
        return 0
    except Exception as e:
        logger.error(f"Error fetching GitHub issue count: {e}")
        return 0


def get_dependabot_prs() -> dict:
    """
    Search for open Dependabot PRs across the MoJ org that require a review
    from the Modernisation Platform team. Returns count and message list with
    CI check status for each PR.
    """
    headers = _get_github_headers()
    if not headers:
        return {"count": 0, "messages": []}

    try:
        search_query = (
            "is:open is:pr archived:false "
            "team-review-requested:ministryofjustice/modernisation-platform "
            "author:app/dependabot "
            "-repo:ministryofjustice/modernisation-platform-environments"
        )

        response = requests.get(
            f"{GITHUB_API_BASE}/search/issues",
            headers=headers,
            params={"q": search_query, "per_page": 100},
            timeout=10,
        )
        if response.status_code != 200:
            logger.error(f"Failed searching for Dependabot PRs: {response.status_code}")
            return {"count": 0, "messages": []}

        prs = response.json().get("items", [])
        messages: list[dict] = []

        for pr in prs:
            repo_full_name = pr["repository_url"].replace(
                "https://api.github.com/repos/", ""
            )
            if repo_full_name == "ministryofjustice/modernisation-platform-environments":
                continue

            check_status = _get_pr_check_status(headers, repo_full_name, pr["number"])
            messages.append(
                {
                    "user": "Dependabot",
                    "user_id": "dependabot",
                    "text": f"{pr['title']} ({repo_full_name})",
                    "full_text": f"Repository: {repo_full_name}\nPR: {pr['title']}\nUpdated: {pr['updated_at']}",
                    "timestamp": pr["updated_at"],
                    "link": pr["html_url"],
                    "check_status": check_status,
                    "repo": repo_full_name,
                    "pr_number": pr["number"],
                }
            )

        logger.info(f"Found {len(messages)} Dependabot PRs requiring team review")
        return {"count": len(messages), "messages": messages}

    except Exception as e:
        logger.error(f"Error fetching Dependabot PRs: {e}", exc_info=True)
        return {"count": 0, "messages": []}


def _get_pr_check_status(headers: dict, repo_full_name: str, pr_number: int) -> str:
    """Return a single status string for the most recent CI checks on a PR head commit."""
    try:
        pr_resp = requests.get(
            f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}",
            headers=headers,
            timeout=5,
        )
        if pr_resp.status_code != 200:
            return "unknown"

        head_sha = pr_resp.json().get("head", {}).get("sha")
        if not head_sha:
            return "unknown"

        runs_resp = requests.get(
            f"{GITHUB_API_BASE}/repos/{repo_full_name}/commits/{head_sha}/check-runs",
            headers=headers,
            timeout=5,
        )
        if runs_resp.status_code != 200:
            return "unknown"

        check_runs = runs_resp.json().get("check_runs", [])
        if not check_runs:
            # Fall back to commit status API
            status_resp = requests.get(
                f"{GITHUB_API_BASE}/repos/{repo_full_name}/commits/{head_sha}/status",
                headers=headers,
                timeout=5,
            )
            if status_resp.status_code == 200:
                return status_resp.json().get("state", "unknown")
            return "unknown"

        # Keep only the most recent run per check name
        latest_runs: dict = {}
        for run in check_runs:
            name = run.get("name")
            started = run.get("started_at", "")
            if name not in latest_runs or started > latest_runs[name].get("started_at", ""):
                latest_runs[name] = run

        statuses = [
            r.get("conclusion") or r.get("status") for r in latest_runs.values()
        ]
        relevant = [s for s in statuses if s not in ("skipped", "neutral")]

        if not relevant:
            return "success"
        if any(s in ("in_progress", "queued", "pending") for s in relevant):
            return "pending"
        if any(s == "failure" for s in relevant):
            return "failure"
        if all(s == "success" for s in relevant):
            return "success"
        if any(s in ("action_required", "cancelled", "timed_out") for s in relevant):
            return "error"
        return "unknown"

    except Exception as e:
        logger.warning(f"Could not fetch check status for PR #{pr_number}: {e}")
        return "unknown"


def get_all_workflow_failures(branch: str = "main") -> dict:
    """
    Return workflows whose most recent run on the given branch failed within
    the last 24 hours.  Workflows where a subsequent run succeeded are excluded.
    """
    headers = _get_github_headers()
    if not headers:
        return {"count": 0, "failures": []}

    try:
        response = requests.get(
            f"{GITHUB_API_BASE}/repos/{GITHUB_ORG}/{GITHUB_REPO}/actions/runs",
            headers=headers,
            params={"branch": branch, "per_page": 100, "status": "completed"},
            timeout=10,
        )
        if response.status_code != 200:
            logger.error(f"Failed to fetch workflow runs: {response.status_code}")
            return {"count": 0, "failures": []}

        all_runs = response.json().get("workflow_runs", [])
        workflows: dict = defaultdict(list)
        for run in all_runs:
            workflows[run["name"]].append(run)

        for name in workflows:
            workflows[name].sort(key=lambda r: r["created_at"], reverse=True)

        cutoff = datetime.utcnow() - timedelta(hours=24)
        failures: list[dict] = []

        for runs in workflows.values():
            most_recent = runs[0]
            run_time = datetime.strptime(most_recent["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            if most_recent["conclusion"] == "failure" and run_time >= cutoff:
                failures.append(
                    {
                        "workflow": most_recent["name"],
                        "run_id": most_recent["id"],
                        "run_number": most_recent["run_number"],
                        "title": (
                            most_recent.get("display_title")
                            or most_recent.get("head_commit", {}).get("message", "")
                        ),
                        "created_at": most_recent["created_at"],
                        "link": most_recent["html_url"],
                        "author": most_recent.get("head_commit", {})
                        .get("author", {})
                        .get("name", "Unknown"),
                    }
                )

        logger.info(f"Found {len(failures)} unfixed workflow failures on {branch}")
        return {"count": len(failures), "failures": failures}

    except Exception as e:
        logger.error(f"Error fetching workflow failures: {e}")
        return {"count": 0, "failures": []}
