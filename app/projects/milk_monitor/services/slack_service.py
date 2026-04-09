import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import requests

from app.shared.config.app_config import app_config

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"

EMOJI_MAP = {
    "red_circle": "🔴",
    "large_green_circle": "🟢",
    "green_circle": "🟢",
    "yellow_circle": "🟡",
    "orange_circle": "🟠",
    "white_circle": "⚪",
    "black_circle": "⚫",
    "large_blue_circle": "🔵",
    "warning": "⚠️",
    "no_entry": "⛔",
    "check_mark": "✅",
    "white_check_mark": "✅",
    "x": "❌",
    "heavy_check_mark": "✔️",
    "eyes": "👀",
    "fire": "🔥",
    "rotating_light": "🚨",
    "bell": "🔔",
    "tada": "🎉",
    "thumbsup": "👍",
    "thumbsdown": "👎",
    "information_source": "ℹ️",
}

COMPLETION_EMOJIS = frozenset(
    [
        "white_check_mark",
        "heavy_check_mark",
        "ballot_box_with_check",
        "white_tick",
        "github-tick",
        "check",
        "checkmark",
        "white-check-mark",
        "green-check",
        "green_check",
        "tick",
        "done",
        "completed",
        "resolved",
        "approved_stamp",
    ]
)

PR_COMPLETION_EMOJIS = frozenset(
    [
        "white_check_mark",
        "heavy_check_mark",
        "ballot_box_with_check",
        "white_tick",
        "approved",
        "approved_stamp",
        "thumbsup",
        "tada",
        "github-tick",
        "check",
        "checkmark",
    ]
)

_user_name_cache: dict[str, str] = {}

# File-based cache for analytics results — shared across Gunicorn workers
ANALYTICS_CACHE_FILE = "/tmp/slack_analytics_cache.json"
ANALYTICS_CACHE_TTL = 1800  # 30 minutes


def convert_slack_emojis(text: str) -> str:
    """Convert Slack emoji codes (e.g. :red_circle:) to Unicode emoji characters."""
    if not text:
        return text

    def replace_emoji(match: re.Match) -> str:
        return EMOJI_MAP.get(match.group(1), match.group(0))

    return re.sub(r":([a-z_]+):", replace_emoji, text)


def _get_auth_headers() -> dict | None:
    token = app_config.slack.bot_token
    if not token:
        logger.warning("SLACK_BOT_TOKEN not configured")
        return None
    return {"Authorization": f"Bearer {token}"}


def _find_channel_id(headers: dict, channel_name: str) -> str | None:
    """Resolve a channel name to its Slack channel ID."""
    try:
        response = requests.get(
            f"{SLACK_API_BASE}/users.conversations",
            headers=headers,
            params={"types": "public_channel,private_channel", "limit": 200},
            timeout=10,
        )
        if response.status_code != 200:
            logger.error(f"Failed to fetch channel list: {response.status_code}")
            return None

        data = response.json()
        if not data.get("ok"):
            logger.error(f"Slack API error listing channels: {data.get('error')}")
            return None

        for channel in data.get("channels", []):
            if channel.get("name") == channel_name:
                return channel.get("id")

        logger.warning(f"Channel '{channel_name}' not found — bot may not be a member.")
        return None
    except Exception as e:
        logger.error(f"Error finding channel ID for '{channel_name}': {e}")
        return None


def get_slack_user_name(user_id: str) -> str:
    """Return the display name for a Slack user ID, with in-process caching."""
    if not user_id:
        return user_id

    if user_id in _user_name_cache:
        return _user_name_cache[user_id]

    headers = _get_auth_headers()
    if not headers:
        return user_id

    try:
        response = requests.get(
            f"{SLACK_API_BASE}/users.info",
            headers=headers,
            params={"user": user_id},
            timeout=5,
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                user = data.get("user", {})
                name = (
                    user.get("profile", {}).get("display_name")
                    or user.get("real_name")
                    or user.get("name")
                    or user_id
                )
                _user_name_cache[user_id] = name
                return name
    except Exception as e:
        logger.error(f"Error fetching Slack user name for {user_id}: {e}")

    _user_name_cache[user_id] = user_id
    return user_id


def _extract_pagerduty_incident_id(text: str) -> str | None:
    """Extract PagerDuty incident ID from message URL."""
    if not text:
        return None
    match = re.search(r'incidents/([A-Z0-9]+)', text)
    return match.group(1) if match else None


def _is_pagerduty_initial_alert(text: str) -> bool:
    """Check if this is the initial triggered alert (has urgency level)."""
    text_lower = text.lower()
    return "urgency:" in text_lower


def _is_pagerduty_closed_alert(text: str) -> bool:
    """Check if the initial PagerDuty alert has transitioned to a closed state."""
    text_lower = text.lower()
    return any(marker in text_lower for marker in (":green_circle:", ":large_green_circle:", "🟢"))

def get_slack_channel_data(channel_name: str) -> dict:
    """
    Return unresolved and completed messages from a Slack channel with activity
    in the past 25 hours.

    For PagerDuty alert channels, only initial incident posts are considered.
    Follow-up status posts are ignored and closure is inferred from the
    initial post state (green indicator means closed).
    """
    headers = _get_auth_headers()
    if not headers:
        return {"count": 0, "messages": [], "completed": []}

    try:
        channel_id = _find_channel_id(headers, channel_name)
        if not channel_id:
            return {"count": 0, "messages": [], "completed": []}

        lookback = int(time.time()) - (25 * 60 * 60)
        all_messages: list[dict] = []
        cursor = None

        for _ in range(3):  # up to 3 pages / 300 messages
            params: dict = {"channel": channel_id, "limit": 100}
            if cursor:
                params["cursor"] = cursor

            response = requests.get(
                f"{SLACK_API_BASE}/conversations.history",
                headers=headers,
                params=params,
                timeout=10,
            )
            if response.status_code != 200:
                break

            data = response.json()
            if not data.get("ok"):
                break

            messages = data.get("messages", [])
            if not messages:
                break

            all_messages.extend(messages)
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        logger.info(f"Fetched {len(all_messages)} messages from #{channel_name}")

        # Check if this is a PagerDuty alert channel
        is_pagerduty_channel = channel_name in [
            "modernisation-platform-sec-hub-high-alerts",
            "modernisation-platform-high-priority-alarms",
        ]

        seen_incidents: set[str] = set()
        unresolved: list[dict] = []
        completed: list[dict] = []

        for msg in all_messages:
            subtype = msg.get("subtype", "")
            bot_id = msg.get("bot_id", "")
            bot_username = msg.get("username", "").lower()
            text = msg.get("text", "")

            if subtype in ("channel_join", "channel_leave"):
                continue

            # PagerDuty-specific logic for alert channels
            if is_pagerduty_channel:
                is_pagerduty = (
                    "pagerduty" in bot_username
                    or "pagerduty" in text.lower()[:100]
                )

                if is_pagerduty:
                    incident_id = _extract_pagerduty_incident_id(text)

                    # Handle initial alert messages
                    if _is_pagerduty_initial_alert(text):
                        # Only include the first occurrence of each incident
                        if incident_id and incident_id in seen_incidents:
                            continue
                        if incident_id:
                            seen_incidents.add(incident_id)
                    else:
                        # Skip other PagerDuty messages (acknowledged, note added, etc.)
                        continue

                else:
                    # Skip all non-PagerDuty messages in PagerDuty alert channels
                    # (human posts, other bots, etc.)
                    continue
            else:
                # Non-PagerDuty channels: filter bot messages as before
                if (subtype == "bot_message" or bot_id):
                    continue

            # Skip thread replies (only show parent messages)
            if msg.get("thread_ts") and msg.get("thread_ts") != msg.get("ts"):
                continue

            msg_ts = float(msg.get("ts", 0))
            is_recent = msg_ts >= lookback

            has_recent_thread = False
            if msg.get("reply_count", 0) > 0:
                latest_reply = float(msg.get("latest_reply", 0))
                has_recent_thread = latest_reply >= lookback

            if not (is_recent or has_recent_thread):
                continue

            reactions = msg.get("reactions", [])
            has_approved = any(r.get("name", "").startswith("approved") for r in reactions)
            has_completion = (
                any(r.get("name") in COMPLETION_EMOJIS for r in reactions) or has_approved
            )

            if is_pagerduty_channel:
                if _is_pagerduty_initial_alert(text) and _is_pagerduty_closed_alert(text):
                    has_completion = True

            completed_by = None
            acknowledged_by = None

            if has_completion:
                for r in reactions:
                    name = r.get("name", "")
                    if name in COMPLETION_EMOJIS or name.startswith("approved"):
                        users = r.get("users", [])
                        if users:
                            completed_by = get_slack_user_name(users[0])
                        break
            else:
                for r in reactions:
                    if r.get("name") == "eyes":
                        users = r.get("users", [])
                        if users:
                            acknowledged_by = get_slack_user_name(users[0])
                        break

            user_id = msg.get("user", "Unknown")
            user_name = get_slack_user_name(user_id)
            text_converted = convert_slack_emojis(text)
            ts_clean = msg.get("ts", "").replace(".", "")
            link = f"https://mojdt.slack.com/archives/{channel_id}/p{ts_clean}"

            message_data: dict = {
                "user": user_name,
                "user_id": user_id,
                "text": text_converted[:200] + ("..." if len(text_converted) > 200 else ""),
                "full_text": text_converted,
                "timestamp": msg.get("ts"),
                "link": link,
            }

            if not has_completion:
                message_data["acknowledged_by"] = acknowledged_by
                unresolved.append(message_data)
            else:
                message_data["completed_by"] = completed_by
                completed.append(message_data)

        unresolved.sort(key=lambda m: float(m.get("timestamp") or 0), reverse=True)
        completed.sort(key=lambda m: float(m.get("timestamp") or 0), reverse=True)

        logger.info(
            f"#{channel_name}: {len(unresolved)} unresolved, {len(completed)} completed"
        )
        return {"count": len(unresolved), "messages": unresolved, "completed": completed}

    except Exception as e:
        logger.error(f"Error fetching Slack channel data for #{channel_name}: {e}", exc_info=True)
        return {"count": 0, "messages": [], "completed": []}


def get_daniel_spaniel_messages(channel_name: str) -> dict:
    """Return Daniel the Spaniel bot messages from the past 25 hours."""
    headers = _get_auth_headers()
    if not headers:
        return {"count": 0, "messages": []}

    try:
        channel_id = _find_channel_id(headers, channel_name)
        if not channel_id:
            return {"count": 0, "messages": []}

        lookback = str(int(time.time()) - (25 * 60 * 60))
        all_messages: list[dict] = []
        cursor = None

        for _ in range(3):  # up to 3 pages / 300 messages
            params: dict = {"channel": channel_id, "oldest": lookback, "limit": 100}
            if cursor:
                params["cursor"] = cursor

            response = requests.get(
                f"{SLACK_API_BASE}/conversations.history",
                headers=headers,
                params=params,
                timeout=10,
            )
            if response.status_code != 200:
                break

            data = response.json()
            if not data.get("ok"):
                break

            batch = data.get("messages", [])
            if not batch:
                break

            all_messages.extend(batch)
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        daniel_names = frozenset(
            ["daniel the manual spaniel", "daniel", "daniel the spaniel"]
        )
        messages: list[dict] = []
        completed: list[dict] = []

        for msg in all_messages:
            bot_id = msg.get("bot_id")
            username = msg.get("username", "").lower()
            text_lower = msg.get("text", "").lower()

            is_daniel = any(name in username for name in daniel_names) or any(
                name in text_lower for name in daniel_names
            ) or ("paw_prints" in text_lower and "friendly manual" in text_lower)

            if is_daniel or (bot_id and "daniel" in username):
                full_text = msg.get("text", "")
                ts = msg.get("ts", "").replace(".", "")

                reactions = msg.get("reactions", [])
                has_approved = any(r.get("name", "").startswith("approved") for r in reactions)
                has_completion = (
                    any(r.get("name") in COMPLETION_EMOJIS for r in reactions) or has_approved
                )

                completed_by = None
                if has_completion:
                    for r in reactions:
                        name = r.get("name", "")
                        if name in COMPLETION_EMOJIS or name.startswith("approved"):
                            users = r.get("users", [])
                            if users:
                                completed_by = get_slack_user_name(users[0])
                            break

                message_data = {
                    "user": msg.get("username", "Daniel the Manual Spaniel"),
                    "user_id": bot_id or "bot",
                    "text": full_text[:200] + ("..." if len(full_text) > 200 else ""),
                    "full_text": full_text,
                    "timestamp": msg.get("ts"),
                    "link": f"https://mojdt.slack.com/archives/{channel_id}/p{ts}",
                }

                if has_completion:
                    message_data["completed_by"] = completed_by
                    completed.append(message_data)
                else:
                    messages.append(message_data)

        logger.info(f"#{channel_name}: {len(messages)} active, {len(completed)} completed Daniel the Spaniel messages")
        return {"count": len(messages), "messages": messages, "completed": completed}

    except Exception as e:
        logger.error(
            f"Error fetching Daniel the Spaniel messages for #{channel_name}: {e}",
            exc_info=True,
        )
        return {"count": 0, "messages": []}


def get_slack_pr_links(channel_name: str) -> dict:
    """Return unresolved and completed GitHub PR links posted in a Slack channel in the past 25 hours."""
    headers = _get_auth_headers()
    if not headers:
        return {"count": 0, "messages": [], "completed": []}

    try:
        channel_id = _find_channel_id(headers, channel_name)
        if not channel_id:
            return {"count": 0, "messages": [], "completed": []}

        lookback = str(int(time.time()) - (25 * 60 * 60))
        response = requests.get(
            f"{SLACK_API_BASE}/conversations.history",
            headers=headers,
            params={"channel": channel_id, "oldest": lookback, "limit": 100},
            timeout=10,
        )
        if response.status_code != 200 or not response.json().get("ok"):
            return {"count": 0, "messages": [], "completed": []}

        pr_pattern = re.compile(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)")
        pr_messages: list[dict] = []
        completed: list[dict] = []

        for msg in response.json().get("messages", []):
            # Skip bots and thread replies
            if msg.get("bot_id") or (
                msg.get("thread_ts") and msg.get("thread_ts") != msg.get("ts")
            ):
                continue

            text = msg.get("text", "")
            pr_links = pr_pattern.findall(text)
            if not pr_links:
                continue

            reactions = msg.get("reactions", [])
            is_completed = any(
                r.get("name") in PR_COMPLETION_EMOJIS or r.get("name", "").startswith("approved")
                for r in reactions
            )

            user_id = msg.get("user", "Unknown")
            user_name = get_slack_user_name(user_id)
            ts_clean = msg.get("ts", "").replace(".", "")
            slack_link = f"https://mojdt.slack.com/archives/{channel_id}/p{ts_clean}"

            if is_completed:
                completed_by = None
                for r in reactions:
                    name = r.get("name", "")
                    if name in PR_COMPLETION_EMOJIS or name.startswith("approved"):
                        users = r.get("users", [])
                        if users:
                            completed_by = get_slack_user_name(users[0])
                        break
                for org, repo, pr_num in pr_links:
                    completed.append(
                        {
                            "user": user_name,
                            "user_id": user_id,
                            "text": f"PR #{pr_num} in {org}/{repo}",
                            "full_text": text,
                            "timestamp": msg.get("ts"),
                            "link": f"https://github.com/{org}/{repo}/pull/{pr_num}",
                            "slack_link": slack_link,
                            "completed_by": completed_by,
                        }
                    )
            else:
                for org, repo, pr_num in pr_links:
                    pr_messages.append(
                        {
                            "user": user_name,
                            "user_id": user_id,
                            "text": f"PR #{pr_num} in {org}/{repo}",
                            "full_text": text,
                            "timestamp": msg.get("ts"),
                            "link": f"https://github.com/{org}/{repo}/pull/{pr_num}",
                            "slack_link": slack_link,
                        }
                    )

        pr_messages.sort(key=lambda m: float(m.get("timestamp") or 0), reverse=True)
        completed.sort(key=lambda m: float(m.get("timestamp") or 0), reverse=True)

        logger.info(f"#{channel_name}: {len(pr_messages)} unresolved PR links, {len(completed)} completed")
        return {"count": len(pr_messages), "messages": pr_messages, "completed": completed}

    except Exception as e:
        logger.error(
            f"Error fetching PR links from #{channel_name}: {e}", exc_info=True
        )
        return {"count": 0, "messages": [], "completed": []}


def get_slack_channel_analytics(channel_name: str, lookback_days: int = 180) -> dict:
    """Return message volume analytics for original posts in a Slack channel."""
    now = time.time()
    cache_key = f"{channel_name}:{lookback_days}"

    if os.path.exists(ANALYTICS_CACHE_FILE):
        try:
            with open(ANALYTICS_CACHE_FILE, "r") as f:
                cache_data = json.load(f)
            cache_age = now - cache_data.get("timestamp", 0)
            if cache_age < ANALYTICS_CACHE_TTL and cache_data.get("key") == cache_key:
                logger.debug(f"Returning cached Slack analytics for #{channel_name}")
                return cache_data["data"]
        except (json.JSONDecodeError, IOError, KeyError):
            pass

    headers = _get_auth_headers()
    if not headers:
        return {
            "error": "SLACK_BOT_TOKEN not configured",
            "counts": {"day": 0, "week": 0, "month": 0},
            "daily_series": [],
            "weekly_series": [],
            "monthly_series": [],
            "hourly_distribution": [],
            "user_leaderboard": [],
            "peak_hour": {"hour": "N/A", "count": 0},
            "total_messages": 0,
            "lookback_days": lookback_days,
        }

    try:
        channel_id = _find_channel_id(headers, channel_name)
        if not channel_id:
            return {
                "error": f"Channel '{channel_name}' not found or bot is not a member",
                "counts": {"day": 0, "week": 0, "month": 0},
                "daily_series": [],
                "weekly_series": [],
                "monthly_series": [],
                "hourly_distribution": [],
                "user_leaderboard": [],
                "peak_hour": {"hour": "N/A", "count": 0},
                "total_messages": 0,
                "lookback_days": lookback_days,
            }

        now_ts = int(time.time())
        now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        oldest_ts = now_ts - (lookback_days * 24 * 60 * 60)
        oldest_dt = datetime.fromtimestamp(oldest_ts, tz=timezone.utc)

        all_messages: list[dict] = []
        cursor = None

        for _ in range(40):  # Up to ~8,000 messages (40 * 200)
            params: dict = {
                "channel": channel_id,
                "oldest": str(oldest_ts),
                "limit": 200,
            }
            if cursor:
                params["cursor"] = cursor

            response = requests.get(
                f"{SLACK_API_BASE}/conversations.history",
                headers=headers,
                params=params,
                timeout=10,
            )
            if response.status_code != 200:
                logger.error(
                    f"Slack history request failed for #{channel_name}: {response.status_code}"
                )
                break

            data = response.json()
            if not data.get("ok"):
                logger.error(
                    f"Slack API error reading #{channel_name} history: {data.get('error')}"
                )
                break

            batch = data.get("messages", [])
            if not batch:
                break

            all_messages.extend(batch)

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        daily_counts: defaultdict[str, int] = defaultdict(int)
        weekly_counts: defaultdict[str, int] = defaultdict(int)
        monthly_counts: defaultdict[str, int] = defaultdict(int)
        hourly_counts: defaultdict[int, int] = defaultdict(int)
        user_counts: Counter[str] = Counter()

        last_day = now_ts - (24 * 60 * 60)
        last_week = now_ts - (7 * 24 * 60 * 60)
        last_month = now_ts - (30 * 24 * 60 * 60)

        count_day = 0
        count_week = 0
        count_month = 0
        total_messages = 0

        for msg in all_messages:
            subtype = msg.get("subtype")
            if subtype or msg.get("bot_id"):
                continue

            if msg.get("thread_ts") and msg.get("thread_ts") != msg.get("ts"):
                continue

            user_id = msg.get("user")
            ts = msg.get("ts")
            if not user_id or not ts:
                continue

            try:
                ts_float = float(ts)
            except (TypeError, ValueError):
                continue

            msg_dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
            msg_date = msg_dt.date()
            week_start = msg_date - timedelta(days=msg_date.weekday())

            total_messages += 1
            user_counts[user_id] += 1
            daily_counts[msg_date.isoformat()] += 1
            weekly_counts[week_start.isoformat()] += 1
            monthly_counts[f"{msg_dt.year}-{msg_dt.month:02d}"] += 1
            hourly_counts[msg_dt.hour] += 1

            if ts_float >= last_day:
                count_day += 1
            if ts_float >= last_week:
                count_week += 1
            if ts_float >= last_month:
                count_month += 1

        daily_series: list[dict] = []
        for day_offset in range(29, -1, -1):
            day = (now_dt - timedelta(days=day_offset)).date().isoformat()
            daily_series.append({"label": day, "count": daily_counts.get(day, 0)})

        this_week_start = now_dt.date() - timedelta(days=now_dt.date().weekday())
        weekly_series: list[dict] = []
        for week_offset in range(11, -1, -1):
            week_start = this_week_start - timedelta(weeks=week_offset)
            week_key = week_start.isoformat()
            weekly_series.append(
                {
                    "label": week_key,
                    "count": weekly_counts.get(week_key, 0),
                }
            )

        current_month = now_dt.year * 12 + (now_dt.month - 1)
        oldest_month = oldest_dt.year * 12 + (oldest_dt.month - 1)
        monthly_window_months = max(1, min(12, (current_month - oldest_month) + 1))
        monthly_series: list[dict] = []
        for month_offset in range(monthly_window_months - 1, -1, -1):
            month_value = current_month - month_offset
            year = month_value // 12
            month = (month_value % 12) + 1
            month_key = f"{year}-{month:02d}"
            monthly_series.append(
                {
                    "label": datetime(year, month, 1).strftime("%b %Y"),
                    "count": monthly_counts.get(month_key, 0),
                }
            )

        hourly_distribution = [
            {
                "hour": f"{hour:02d}:00-{(hour + 1) % 24:02d}:00",
                "count": hourly_counts.get(hour, 0),
            }
            for hour in range(24)
        ]

        peak_hour_int = 0
        peak_hour_count = 0
        if hourly_counts:
            peak_hour_int, peak_hour_count = max(
                hourly_counts.items(), key=lambda item: item[1]
            )

        user_leaderboard: list[dict] = []
        for user_id, count in user_counts.most_common(15):
            user_leaderboard.append(
                {
                    "user_id": user_id,
                    "user_name": get_slack_user_name(user_id),
                    "count": count,
                }
            )

        logger.info(
            f"Slack analytics for #{channel_name}: {total_messages} original messages in {lookback_days} days"
        )

        result = {
            "error": None,
            "channel": channel_name,
            "channel_id": channel_id,
            "counts": {"day": count_day, "week": count_week, "month": count_month},
            "daily_series": daily_series,
            "weekly_series": weekly_series,
            "monthly_series": monthly_series,
            "monthly_window_months": monthly_window_months,
            "hourly_distribution": hourly_distribution,
            "user_leaderboard": user_leaderboard,
            "peak_hour": {
                "hour": f"{peak_hour_int:02d}:00-{(peak_hour_int + 1) % 24:02d}:00",
                "count": peak_hour_count,
            },
            "total_messages": total_messages,
            "lookback_days": lookback_days,
        }

        try:
            with open(ANALYTICS_CACHE_FILE, "w") as f:
                json.dump({"key": cache_key, "data": result, "timestamp": now}, f)
        except IOError:
            pass

        return result

    except Exception as e:
        logger.error(
            f"Error building analytics for #{channel_name}: {e}",
            exc_info=True,
        )
        return {
            "error": "Unable to fetch Slack analytics",
            "counts": {"day": 0, "week": 0, "month": 0},
            "daily_series": [],
            "weekly_series": [],
            "monthly_series": [],
            "monthly_window_months": 0,
            "hourly_distribution": [],
            "user_leaderboard": [],
            "peak_hour": {"hour": "N/A", "count": 0},
            "total_messages": 0,
            "lookback_days": lookback_days,
        }
