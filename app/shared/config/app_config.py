import os
from types import SimpleNamespace


def __get_env_var(name: str) -> str | None:
    return os.getenv(name)


def __get_env_var_as_boolean(name: str, default: bool) -> bool | None:
    value = __get_env_var(name)

    if value is None:
        return default

    if value.lower() == "true":
        return True

    if value.lower() == "false":
        return False

    return default


app_config = SimpleNamespace(
    auth_enabled=__get_env_var_as_boolean("AUTH_ENABLED", default=True),
    auth0=SimpleNamespace(
        domain=__get_env_var("AUTH0_DOMAIN"),
        client_id=__get_env_var("AUTH0_CLIENT_ID"),
        client_secret=__get_env_var("AUTH0_CLIENT_SECRET"),
    ),
    flask=SimpleNamespace(
        app_secret_key=__get_env_var("APP_SECRET_KEY"),
    ),
    logging_level=__get_env_var("LOGGING_LEVEL"),
    phase_banner_text=__get_env_var("PHASE_BANNER_TEXT"),
    github=SimpleNamespace(
        app=SimpleNamespace(
            client_id=__get_env_var("GITHUB_APP_CLIENT_ID"),
            installation_id=int(__get_env_var("GITHUB_APP_INSTALLATION_ID") or 0),
            private_key=__get_env_var("GITHUB_APP_PRIVATE_KEY"),
        ),
        token=__get_env_var("ADMIN_GITHUB_TOKEN"),
    ),
    sentry=SimpleNamespace(
        dsn_key=__get_env_var("SENTRY_DSN_KEY"), environment=__get_env_var("SENTRY_ENV")
    ),
)
