"""Version check API for detecting updates from GitHub Releases."""

import json
import re
import time
import urllib.error
import urllib.request
from typing_extensions import TypedDict

from fastapi import APIRouter

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.schemas import VersionCheckResponse
from AutoGLM_GUI.version import APP_VERSION


class GitHubRelease(TypedDict, total=False):
    """GitHub Release API response structure."""

    tag_name: str
    html_url: str
    published_at: str


class _VersionCache(TypedDict):
    """Internal cache structure for version checking."""

    data: VersionCheckResponse | None
    timestamp: float
    ttl: int


router = APIRouter()

# In-memory cache for version check results
_version_cache: _VersionCache = {
    "data": None,
    "timestamp": 0,
    "ttl": 3600,
}

# GitHub repository information
GITHUB_REPO = "suyiiyii/AutoGLM-GUI"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def parse_version(version_str: str) -> tuple[int, ...] | None:
    """
    Parse semantic version string into tuple of integers.

    Args:
        version_str: Version string like "0.4.12" or "v0.5.0"

    Returns:
        Tuple of version numbers like (0, 4, 12) or None if invalid
    """
    # Handle dev/unknown versions
    if version_str in ("dev", "unknown", "..."):
        return None

    # Strip 'v' prefix if present
    version_str = version_str.lstrip("v")

    # Remove pre-release tags (e.g., "-beta", "-rc1")
    version_str = re.split(r"[-+]", version_str)[0]

    try:
        return tuple(int(x) for x in version_str.split("."))
    except (ValueError, AttributeError):
        logger.warning(f"Failed to parse version: {version_str}")
        return None


def compare_versions(current: str, latest: str) -> bool:
    """
    Compare two semantic versions.

    Args:
        current: Current version string
        latest: Latest version string

    Returns:
        True if update is available (latest > current), False otherwise
    """
    current_tuple = parse_version(current)
    latest_tuple = parse_version(latest)

    # If either version is invalid, assume no update
    if current_tuple is None or latest_tuple is None:
        return False

    return latest_tuple > current_tuple


def fetch_latest_release() -> GitHubRelease | None:
    """Fetch latest release information from GitHub API."""
    try:
        # Create request with User-Agent header (required by GitHub API)
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"User-Agent": f"AutoGLM-GUI/{APP_VERSION}"},
        )

        # Fetch data with 10-second timeout
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            logger.debug(
                f"Successfully fetched latest release: {data.get('tag_name', 'unknown')}"
            )
            return data

    except urllib.error.HTTPError as e:
        if e.code == 403:
            logger.warning(
                "GitHub API rate limit exceeded (HTTP 403), using cached data if available"
            )
        else:
            logger.warning(f"GitHub API HTTP error {e.code}: {e.reason}")
        return None

    except urllib.error.URLError as e:
        logger.warning(f"Network error fetching latest release: {e.reason}")
        return None

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse GitHub API response: {e}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error fetching latest release: {e}")
        return None


@router.get("/api/version/latest", response_model=VersionCheckResponse)
def check_version() -> VersionCheckResponse:
    """
    Check for available updates from GitHub Releases.

    Returns version comparison results with caching to minimize API calls.
    Cache TTL is 1 hour to stay within GitHub API rate limits (60 req/hour).

    Returns:
        VersionCheckResponse with update information
    """
    current_time = time.time()

    # Check if cache is still valid
    if (
        _version_cache["data"] is not None
        and current_time - _version_cache["timestamp"] < _version_cache["ttl"]
    ):
        logger.debug(
            f"Using cached version check result (age: {int(current_time - _version_cache['timestamp'])}s)"
        )
        return _version_cache["data"]

    # Fetch latest release from GitHub
    release_data = fetch_latest_release()

    if release_data is None:
        # If fetch failed, check if we have cached data to fall back to
        if _version_cache["data"] is not None:
            logger.warning("Using stale cached data due to fetch failure")
            return _version_cache["data"]

        # No cache available, return safe defaults
        response = VersionCheckResponse(
            current_version=APP_VERSION,
            latest_version=None,
            has_update=False,
            release_url=None,
            published_at=None,
            error="Failed to fetch latest version from GitHub",
        )
        logger.info("Version check failed, returning safe defaults")
        return response

    # Extract version information from release data
    tag_name = release_data.get("tag_name", "")
    latest_version = tag_name.lstrip("v")  # Strip 'v' prefix
    release_url = release_data.get("html_url")
    published_at = release_data.get("published_at")

    # Compare versions
    has_update = compare_versions(APP_VERSION, latest_version)

    # Build response
    response = VersionCheckResponse(
        current_version=APP_VERSION,
        latest_version=latest_version,
        has_update=has_update,
        release_url=release_url,
        published_at=published_at,
        error=None,
    )

    # Update cache
    _version_cache["data"] = response
    _version_cache["timestamp"] = current_time

    logger.info(
        f"Version check completed: current={APP_VERSION}, latest={latest_version}, has_update={has_update}"
    )

    return response
