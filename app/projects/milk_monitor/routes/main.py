import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template

from app.projects.milk_monitor.services import github_service, slack_service
from app.shared.middleware.auth import requires_auth

logger = logging.getLogger(__name__)

milk_monitor_main = Blueprint("milk_monitor_main", __name__)

GITHUB_ORG = "ministryofjustice"
GITHUB_REPO = "modernisation-platform"

CORE_RESPONSIBILITIES = [
    {
        "id": "slack_ask_modernisation",
        "title": "Monitor #ask-modernisation-platform channel",
        "description": "Respond to queries. Liaise with team members. Ensure all requests are responded to.",
        "priority": "high",
        "type": "slack_channel",
        "channel": "ask-modernisation-platform",
        "link": "https://mojdt.slack.com/archives/ask-modernisation-platform",
        "link_text": "Open in Slack",
    },
    {
        "id": "slack_high_priority_alarms",
        "title": "Handle high priority incidents",
        "description": "Check #modernisation-platform-high-priority-alarms. Use runbooks for guidance.",
        "priority": "critical",
        "type": "slack_channel",
        "channel": "modernisation-platform-high-priority-alarms",
        "link": "https://mojdt.slack.com/archives/modernisation-platform-high-priority-alarms",
        "link_text": "Open in Slack",
    },
    {
        "id": "slack_security_hub",
        "title": "Respond to Security Hub alerts",
        "description": "Monitor #modernisation-platform-sec-hub-high-alerts. Follow the Security Hub Slack Alerts runbook.",
        "priority": "high",
        "type": "slack_channel",
        "channel": "modernisation-platform-sec-hub-high-alerts",
        "link": "https://mojdt.slack.com/archives/modernisation-platform-sec-hub-high-alerts",
        "link_text": "Open in Slack",
    },
]

OPTIONAL_RESPONSIBILITIES = [
    {
        "id": "team_pr_reviews",
        "title": "Review team PRs",
        "description": "Review pull requests shared in #modernisation-platform Slack channel.",
        "priority": "medium",
        "type": "slack_pr_links",
        "channel": "modernisation-platform",
        "link": "https://mojdt.slack.com/archives/modernisation-platform",
        "link_text": "View in Slack",
    },
    {
        "id": "workflow_failures",
        "title": "Review failed GitHub workflows on main",
        "description": "Check all workflows in modernisation-platform for failures on main in the last 24 hours.",
        "priority": "high",
        "type": "github_all_workflows",
        "branch": "main",
        "link": f"https://github.com/{GITHUB_ORG}/{GITHUB_REPO}/actions?query=branch%3Amain+is%3Afailure",
        "link_text": "View All Workflows",
    },
    {
        "id": "documentation_updates",
        "title": "Update documentation flagged by Daniel the Spaniel",
        "description": "Check for Daniel the Spaniel bot messages indicating stale documentation.",
        "priority": "medium",
        "type": "daniel_spaniel",
        "channel": "modernisation-platform",
        "link": "https://mojdt.slack.com/archives/modernisation-platform",
        "link_text": "View in Slack",
    },
    {
        "id": "dependabot_prs",
        "title": "Review Dependabot PRs",
        "description": "Review and merge Dependabot dependency updates across the MoJ organisation.",
        "priority": "medium",
        "type": "dependabot_search",
        "link": (
            "https://github.com/search?q=is%3Aopen+is%3Apr+archived%3Afalse"
            "+team-review-requested%3Aministryofjustice%2Fmodernisation-platform"
            "+author%3Aapp%2Fdependabot"
            "+-repo%3Aministryofjustice%2Fmodernisation-platform-environments"
            "&type=pullrequests"
        ),
        "link_text": "View in GitHub",
    },
    {
        "id": "review_state_issues",
        "title": "Review issues in For Review state",
        "description": "Check if issues meet the Definition of Done before moving them to Done.",
        "priority": "medium",
        "type": "github_issues",
        "label": "for-review",
        "link": (
            "https://github.com/orgs/ministryofjustice/projects/17/views/4"
            "?filterQuery=sprint%3A%40current+-status%3A%22Done+in+Sprint%22+status%3A%22For+Review%22"
        ),
        "link_text": "View Project Board",
    },
]


def _format_slack_ts(ts: str | None) -> str:
    """Convert a Slack message timestamp (Unix float string) to a readable time."""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%d %b %H:%M")
    except (ValueError, TypeError):
        return ts


def _format_github_ts(ts: str | None) -> str:
    """Convert a GitHub ISO timestamp string to a readable time."""
    if not ts:
        return ""
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").strftime("%d %b %H:%M")
    except (ValueError, TypeError):
        return ts


def _annotate_times(messages: list[dict], ts_formatter) -> list[dict]:
    """Add a human-readable 'time' field to each message dict in-place."""
    for msg in messages:
        msg["time"] = ts_formatter(msg.get("timestamp"))
    return messages


TABLE_TYPE_MAP = {
    "slack_channel": "slack",
    "slack_pr_links": "pr_links",
    "daniel_spaniel": "slack",
    "github_all_workflows": "workflows",
    "dependabot_search": "dependabot",
    "github_issues": "issues",
}


def _fetch_task_data(task: dict) -> dict:
    """Fetch live data for a single responsibility and return a display-ready dict."""
    task_type = task.get("type", "")
    base = {
        "id": task["id"],
        "title": task["title"],
        "description": task["description"],
        "priority": task["priority"],
        "type": task_type,
        "table_type": TABLE_TYPE_MAP.get(task_type, "manual"),
        "link": task.get("link"),
        "link_text": task.get("link_text", "Open Link"),
    }

    try:
        if task_type == "slack_channel":
            result = slack_service.get_slack_channel_data(task["channel"])
            count = result["count"]
            return {
                **base,
                "count": count,
                "messages": _annotate_times(result.get("messages", []), _format_slack_ts),
                "completed": _annotate_times(result.get("completed", []), _format_slack_ts),
                "status": "requires_attention" if count > 0 else "ok",
            }

        if task_type == "slack_pr_links":
            result = slack_service.get_slack_pr_links(task["channel"])
            count = result["count"]
            return {
                **base,
                "count": count,
                "messages": _annotate_times(result.get("messages", []), _format_slack_ts),
                "status": "requires_attention" if count > 0 else "ok",
            }

        if task_type == "daniel_spaniel":
            result = slack_service.get_daniel_spaniel_messages(task["channel"])
            count = result["count"]
            return {
                **base,
                "count": count,
                "messages": _annotate_times(result.get("messages", []), _format_slack_ts),
                "status": "requires_attention" if count > 0 else "ok",
            }

        if task_type == "github_all_workflows":
            result = github_service.get_all_workflow_failures(task.get("branch", "main"))
            count = result["count"]
            messages = [
                {
                    "user": f["author"],
                    "user_id": "github",
                    "text": f"{f['workflow']} — {f['title'][:100]}",
                    "timestamp": f["created_at"],
                    "time": _format_github_ts(f["created_at"]),
                    "link": f["link"],
                }
                for f in result.get("failures", [])
            ]
            return {
                **base,
                "count": count,
                "messages": messages,
                "status": "requires_attention" if count > 0 else "ok",
            }

        if task_type == "dependabot_search":
            result = github_service.get_dependabot_prs()
            count = result["count"]
            messages = result.get("messages", [])
            for msg in messages:
                msg["time"] = _format_github_ts(msg.get("timestamp"))
            return {
                **base,
                "count": count,
                "messages": messages,
                "status": "requires_attention" if count > 0 else "ok",
            }

        if task_type == "github_issues":
            count = github_service.get_github_issue_count(task.get("label"))
            return {
                **base,
                "count": count,
                "messages": [],
                "status": "requires_attention" if count > 0 else "ok",
            }

        return {**base, "count": 0, "messages": [], "status": "manual_check"}

    except Exception as e:
        logger.error(f"Error fetching task data for {task['id']}: {e}", exc_info=True)
        return {**base, "count": 0, "messages": [], "completed": [], "status": "error"}


@milk_monitor_main.route("/", methods=["GET"])
@requires_auth
def index():
    return render_template("projects/milk_monitor/pages/home.html")


@milk_monitor_main.route("/milk-monitor-dashboard", methods=["GET"])
@requires_auth
def milk_monitor_dashboard():
    all_tasks = [("core", t) for t in CORE_RESPONSIBILITIES] + [
        ("optional", t) for t in OPTIONAL_RESPONSIBILITIES
    ]

    core_tasks: list[dict] = []
    optional_tasks: list[dict] = []
    total_count = 0

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {executor.submit(_fetch_task_data, t): (group, t) for group, t in all_tasks}
        for future in as_completed(future_map):
            group, task = future_map[future]
            try:
                result = future.result()
                total_count += result.get("count", 0)
                if group == "core":
                    core_tasks.append(result)
                else:
                    optional_tasks.append(result)
            except Exception as e:
                logger.error(f"Task {task['id']} raised an exception: {e}")

    # Restore the original declared order
    core_order = {t["id"]: i for i, t in enumerate(CORE_RESPONSIBILITIES)}
    optional_order = {t["id"]: i for i, t in enumerate(OPTIONAL_RESPONSIBILITIES)}
    core_tasks.sort(key=lambda t: core_order.get(t["id"], 999))
    optional_tasks.sort(key=lambda t: optional_order.get(t["id"], 999))

    all_results = core_tasks + optional_tasks
    status_counts = {
        "red":   sum(1 for t in all_results if t["status"] == "requires_attention"),
        "green": sum(1 for t in all_results if t["status"] == "ok"),
        "amber": sum(1 for t in all_results if t["status"] not in ("requires_attention", "ok")),
    }

    return render_template(
        "projects/milk_monitor/pages/milk_monitor_dashboard.html",
        core_tasks=core_tasks,
        optional_tasks=optional_tasks,
        total_count=total_count,
        status_counts=status_counts,
        fetched_at=datetime.now(tz=timezone.utc).strftime("%H:%M UTC"),
    )


@milk_monitor_main.route("/data", methods=["GET"])
@requires_auth
def milk_monitor_data():
    """Lightweight JSON endpoint for polling — returns status and count per task only."""
    all_tasks = [("core", t) for t in CORE_RESPONSIBILITIES] + [
        ("optional", t) for t in OPTIONAL_RESPONSIBILITIES
    ]

    results: list[dict] = []
    total_count = 0

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {executor.submit(_fetch_task_data, t): t for _, t in all_tasks}
        for future in as_completed(future_map):
            task = future_map[future]
            try:
                result = future.result()
                total_count += result.get("count", 0)
                results.append({
                    "id": result["id"],
                    "type": result.get("type", ""),
                    "table_type": result.get("table_type", "manual"),
                    "status": result["status"],
                    "count": result["count"],
                    "messages": result.get("messages", []),
                    "completed": result.get("completed", []),
                })
            except Exception as e:
                logger.error(f"Data endpoint: task {task['id']} failed: {e}")

    status_counts = {
        "red":   sum(1 for r in results if r["status"] == "requires_attention"),
        "green": sum(1 for r in results if r["status"] == "ok"),
        "amber": sum(1 for r in results if r["status"] not in ("requires_attention", "ok")),
    }

    return jsonify({
        "total_count": total_count,
        "status_counts": status_counts,
        "tasks": results,
        "fetched_at": datetime.now(tz=timezone.utc).strftime("%H:%M UTC"),
    })
