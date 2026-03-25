import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests

from app.shared.services.github_app_auth_service import get_github_headers

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_ORG = "ministryofjustice"
GITHUB_REPO = "modernisation-platform"
GITHUB_TEAM_SLUG = "modernisation-platform-engineers"
PROJECT_FOR_REVIEW_ORG = "ministryofjustice"
PROJECT_FOR_REVIEW_NUMBER = 17
PROJECT_STATUS_FIELD_NAME = "Status"
PROJECT_FOR_REVIEW_VALUE = "For Review"

EXCLUDED_TEAM_MEMBERS = frozenset(
    ["dms1981", "davidkelliott", "modernisation-platform-ci"]
)

_team_members_cache: dict = {"members": [], "timestamp": None}
_project_review_transition_cache: dict = {
    "item_ids": set(),
    "initialized": False,
    "timestamp": None,
}


def _normalize_status_value(value: str | None) -> str:
    """Normalize project status values for robust comparisons."""
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def _is_current_iteration(start_date: str | None, duration_days: int | None) -> bool:
    """Return True when an iteration window contains today's UTC date."""
    if not start_date or not duration_days:
        return False

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        return False

    today = datetime.utcnow().date()
    delta_days = (today - start).days
    return 0 <= delta_days < int(duration_days)


def _fetch_project_for_review_items(
    org: str = PROJECT_FOR_REVIEW_ORG,
    project_number: int = PROJECT_FOR_REVIEW_NUMBER,
    status_field_name: str = PROJECT_STATUS_FIELD_NAME,
    status_value: str = PROJECT_FOR_REVIEW_VALUE,
    current_sprint_only: bool = False,
) -> dict:
    """Return project items currently in the configured For Review status."""
    headers = get_github_headers()
    if not headers:
        return {"count": 0, "item_ids": [], "items": []}

    headers = {
        **headers,
        "Accept": "application/vnd.github+json",
    }

    query = """
    query($org: String!, $number: Int!, $cursor: String) {
      organization(login: $org) {
        projectV2(number: $number) {
          items(first: 100, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              content {
                ... on Issue {
                  title
                  url
                  number
                                    updatedAt
                  repository {
                    nameWithOwner
                  }
                }
              }
              fieldValues(first: 20) {
                nodes {
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field {
                      ... on ProjectV2SingleSelectField {
                        name
                      }
                    }
                  }
                                    ... on ProjectV2ItemFieldIterationValue {
                                        title
                                        startDate
                                        duration
                                    }
                }
              }
            }
          }
        }
      }
    }
    """

    review_items: list[dict] = []
    review_item_ids: list[str] = []
    cursor = None
    target_status = _normalize_status_value(status_value)
    target_field = _normalize_status_value(status_field_name)

    try:
        while True:
            response = requests.post(
                f"{GITHUB_API_BASE}/graphql",
                headers=headers,
                json={
                    "query": query,
                    "variables": {
                        "org": org,
                        "number": project_number,
                        "cursor": cursor,
                    },
                },
                timeout=15,
            )

            if response.status_code != 200:
                logger.error(
                    "Failed to fetch project items: status=%s project=%s/%s",
                    response.status_code,
                    org,
                    project_number,
                )
                return {"count": 0, "item_ids": [], "items": []}

            payload = response.json()
            if payload.get("errors"):
                logger.error("GraphQL errors fetching project items: %s", payload["errors"])
                return {"count": 0, "item_ids": [], "items": []}

            project = payload.get("data", {}).get("organization", {}).get("projectV2")
            if not project:
                logger.warning("Project not found for %s/%s", org, project_number)
                return {"count": 0, "item_ids": [], "items": []}

            items_conn = project.get("items", {})
            nodes = items_conn.get("nodes", [])

            for node in nodes:
                item_id = node.get("id")
                content = node.get("content") or {}
                if not item_id or not content:
                    continue

                current_status = None
                in_current_iteration = False
                for fv in (node.get("fieldValues") or {}).get("nodes", []):
                    if _is_current_iteration(fv.get("startDate"), fv.get("duration")):
                        in_current_iteration = True

                    field_name = _normalize_status_value(
                        (fv.get("field") or {}).get("name")
                    )
                    if field_name == target_field:
                        current_status = _normalize_status_value(fv.get("name"))

                if current_sprint_only and not in_current_iteration:
                    continue

                if current_status != target_status:
                    continue

                review_item_ids.append(item_id)
                review_items.append(
                    {
                        "item_id": item_id,
                        "title": content.get("title", "Untitled issue"),
                        "url": content.get("url"),
                        "number": content.get("number"),
                        "updated_at": content.get("updatedAt"),
                        "repo": (content.get("repository") or {}).get("nameWithOwner", ""),
                    }
                )

            page_info = items_conn.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                break

        return {
            "count": len(review_item_ids),
            "item_ids": review_item_ids,
            "items": review_items,
        }

    except Exception as e:
        logger.error(f"Error fetching project For Review items: {e}", exc_info=True)
        return {"count": 0, "item_ids": [], "items": []}


def get_project_for_review_count(
    org: str = PROJECT_FOR_REVIEW_ORG,
    project_number: int = PROJECT_FOR_REVIEW_NUMBER,
    status_field_name: str = PROJECT_STATUS_FIELD_NAME,
    status_value: str = PROJECT_FOR_REVIEW_VALUE,
    current_sprint_only: bool = False,
) -> dict:
    """Return count and IDs for issues currently in For Review on a GitHub Project V2 board."""
    return _fetch_project_for_review_items(
        org=org,
        project_number=project_number,
        status_field_name=status_field_name,
        status_value=status_value,
        current_sprint_only=current_sprint_only,
    )


def detect_project_review_transitions(
    current_item_ids: list[str],
    current_items: list[dict] | None = None,
) -> dict:
    """Compare with previous poll and return newly-moved project items in For Review."""
    global _project_review_transition_cache

    if current_items is None:
        current_items = []

    current_set = set(current_item_ids)
    previous_set: set[str] = _project_review_transition_cache["item_ids"]
    initialized = _project_review_transition_cache["initialized"]

    if not initialized:
        newly_moved_ids = set(current_set)
    else:
        newly_moved_ids = current_set - previous_set

    newly_moved_items = [
        item
        for item in current_items
        if item.get("item_id") in newly_moved_ids
    ]

    _project_review_transition_cache = {
        "item_ids": current_set,
        "initialized": True,
        "timestamp": datetime.utcnow(),
    }

    return {
        "new_count": len(newly_moved_ids),
        "new_items": newly_moved_items,
        "current_count": len(current_set),
    }


def get_team_members() -> list[str]:
    """Return active team members, excluding known departed members. Cached for 1 hour."""
    global _team_members_cache

    if _team_members_cache["timestamp"]:
        age = (datetime.utcnow() - _team_members_cache["timestamp"]).total_seconds()
        if age < 3600:
            return _team_members_cache["members"]

    headers = get_github_headers()
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
    headers = get_github_headers()
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
    headers = get_github_headers()
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

        prs = [
            pr for pr in response.json().get("items", [])
            if pr["repository_url"].replace("https://api.github.com/repos/", "")
            != "ministryofjustice/modernisation-platform-environments"
        ]

        def _build_pr_message(pr: dict) -> dict:
            repo_full_name = pr["repository_url"].replace(
                "https://api.github.com/repos/", ""
            )
            check_status = _get_pr_check_status(headers, repo_full_name, pr["number"])
            return {
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

        messages: list[dict] = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_build_pr_message, pr): pr for pr in prs}
            for future in as_completed(futures):
                try:
                    messages.append(future.result())
                except Exception as e:
                    pr = futures[future]
                    logger.warning(f"Failed to fetch check status for PR #{pr['number']}: {e}")

        # Restore stable ordering (newest updated first)
        messages.sort(key=lambda m: m["timestamp"], reverse=True)

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
    headers = get_github_headers()
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
