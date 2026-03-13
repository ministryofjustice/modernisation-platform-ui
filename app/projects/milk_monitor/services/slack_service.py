import logging
import re
import time

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


def get_slack_channel_data(channel_name: str) -> dict:
    """
    Return unresolved and completed messages from a Slack channel with activity
    in the past 25 hours.

    A message is considered resolved when it has a completion emoji reaction
    (e.g. ✅).  The 👀 reaction indicates acknowledgement without resolution.
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

        unresolved: list[dict] = []
        completed: list[dict] = []

        for msg in all_messages:
            subtype = msg.get("subtype", "")
            bot_id = msg.get("bot_id", "")
            bot_username = msg.get("username", "").lower()

            if subtype in ("channel_join", "channel_leave"):
                continue

            # Special case: allow PagerDuty alerts in the sec-hub channel
            is_pagerduty_sechub = channel_name == "modernisation-platform-sec-hub-high-alerts" and (
                "pagerduty" in bot_username
                or "pagerduty" in msg.get("text", "").lower()[:100]
            )
            if (subtype == "bot_message" or bot_id) and not is_pagerduty_sechub:
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
            text = convert_slack_emojis(msg.get("text", ""))
            ts_clean = msg.get("ts", "").replace(".", "")
            link = f"https://mojdt.slack.com/archives/{channel_id}/p{ts_clean}"

            message_data: dict = {
                "user": user_name,
                "user_id": user_id,
                "text": text[:200] + ("..." if len(text) > 200 else ""),
                "full_text": text,
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
        response = requests.get(
            f"{SLACK_API_BASE}/conversations.history",
            headers=headers,
            params={"channel": channel_id, "oldest": lookback, "limit": 100},
            timeout=10,
        )
        if response.status_code != 200 or not response.json().get("ok"):
            return {"count": 0, "messages": []}

        daniel_names = frozenset(
            ["daniel the manual spaniel", "daniel", "daniel the spaniel"]
        )
        messages: list[dict] = []

        for msg in response.json().get("messages", []):
            bot_id = msg.get("bot_id")
            username = msg.get("username", "").lower()
            text_lower = msg.get("text", "").lower()

            is_daniel = any(name in username for name in daniel_names) or any(
                name in text_lower for name in daniel_names
            ) or ("paw_prints" in text_lower and "friendly manual" in text_lower)

            if is_daniel or (bot_id and "daniel" in username):
                full_text = msg.get("text", "")
                ts = msg.get("ts", "").replace(".", "")
                messages.append(
                    {
                        "user": msg.get("username", "Daniel the Manual Spaniel"),
                        "user_id": bot_id or "bot",
                        "text": full_text[:200] + ("..." if len(full_text) > 200 else ""),
                        "full_text": full_text,
                        "timestamp": msg.get("ts"),
                        "link": f"https://mojdt.slack.com/archives/{channel_id}/p{ts}",
                    }
                )

        logger.info(f"#{channel_name}: {len(messages)} Daniel the Spaniel messages")
        return {"count": len(messages), "messages": messages}

    except Exception as e:
        logger.error(
            f"Error fetching Daniel the Spaniel messages for #{channel_name}: {e}",
            exc_info=True,
        )
        return {"count": 0, "messages": []}


def get_slack_pr_links(channel_name: str) -> dict:
    """Return unresolved GitHub PR links posted in a Slack channel in the past 25 hours."""
    headers = _get_auth_headers()
    if not headers:
        return {"count": 0, "messages": []}

    try:
        channel_id = _find_channel_id(headers, channel_name)
        if not channel_id:
            return {"count": 0, "messages": []}

        lookback = str(int(time.time()) - (25 * 60 * 60))
        response = requests.get(
            f"{SLACK_API_BASE}/conversations.history",
            headers=headers,
            params={"channel": channel_id, "oldest": lookback, "limit": 100},
            timeout=10,
        )
        if response.status_code != 200 or not response.json().get("ok"):
            return {"count": 0, "messages": []}

        pr_pattern = re.compile(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)")
        pr_messages: list[dict] = []

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
            if any(
                r.get("name") in PR_COMPLETION_EMOJIS or r.get("name", "").startswith("approved")
                for r in reactions
            ):
                continue

            user_id = msg.get("user", "Unknown")
            user_name = get_slack_user_name(user_id)
            ts_clean = msg.get("ts", "").replace(".", "")
            slack_link = f"https://mojdt.slack.com/archives/{channel_id}/p{ts_clean}"

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

        logger.info(f"#{channel_name}: {len(pr_messages)} unresolved PR links")
        return {"count": len(pr_messages), "messages": pr_messages}

    except Exception as e:
        logger.error(
            f"Error fetching PR links from #{channel_name}: {e}", exc_info=True
        )
        return {"count": 0, "messages": []}
