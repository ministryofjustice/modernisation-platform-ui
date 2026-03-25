import logging

from app.shared.config.app_config import app_config
from github import Auth, GithubIntegration

logger = logging.getLogger(__name__)


def get_github_headers() -> dict:
    """
    Returns GitHub API auth headers.
    Uses ADMIN_GITHUB_TOKEN if set (local dev override),
    otherwise uses GitHub App authentication (default/production).
    """
    if app_config.github.token:
        logger.info("Using ADMIN_GITHUB_TOKEN for GitHub auth (local dev override)")
        return {
            "Authorization": f"token {app_config.github.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    client_id = app_config.github.app.client_id
    logger.info(
        f"Authenticating via GitHub App (client_id: {client_id[:10]}..., installation_id: {app_config.github.app.installation_id})"
    )

    auth = Auth.AppAuth(client_id, app_config.github.app.private_key)
    gi = GithubIntegration(auth=auth)
    token = gi.get_access_token(app_config.github.app.installation_id).token

    return {"Authorization": f"token {token}"}
