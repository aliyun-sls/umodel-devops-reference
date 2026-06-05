"""python-gitlab client wrapper with soft import."""

import logging

logger = logging.getLogger(__name__)

try:
    import gitlab  # type: ignore

    GITLAB_SDK_AVAILABLE = True
except ModuleNotFoundError:
    gitlab = None  # type: ignore
    GITLAB_SDK_AVAILABLE = False


def create_gitlab_client(url: str, access_token: str):
    """Return a python-gitlab client or None if the SDK is missing."""
    if not GITLAB_SDK_AVAILABLE:
        logger.warning("python-gitlab is not installed; GitLab adapter disabled")
        return None
    return gitlab.Gitlab(url=url, private_token=access_token)
