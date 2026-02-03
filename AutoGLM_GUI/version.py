"""Package version helper."""

from importlib.metadata import version as get_version


def _get_app_version() -> str:
    """Get application version from package metadata."""
    try:
        return get_version("autoglm-gui")
    except Exception:
        return "dev"


APP_VERSION: str = _get_app_version()
