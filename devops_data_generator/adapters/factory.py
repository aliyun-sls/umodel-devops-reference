"""Adapter factory: instantiate a git provider adapter by type name."""

import logging
from typing import Any, Dict

from .base import IGitAdapter

logger = logging.getLogger(__name__)


_SUPPORTED_PROVIDERS = ("gitlab", "codeup")


def create_git_adapter(provider_type: str, config: Dict[str, Any]) -> IGitAdapter:
    """Return an IGitAdapter implementation for ``provider_type``.

    Supported values:
        - "gitlab" → GitLabAdapter (python-gitlab SDK)
        - "codeup" → CodeupAdapter (alibabacloud_devops20210625 SDK)
    """
    provider_type = (provider_type or "").lower()
    if provider_type == "gitlab":
        from .gitlab import GitLabAdapter

        return GitLabAdapter(config)
    if provider_type in ("codeup", "aliyun"):
        from .codeup import CodeupAdapter

        return CodeupAdapter(config)
    raise ValueError(
        f"Unsupported git_provider type '{provider_type}'. "
        f"Supported: {_SUPPORTED_PROVIDERS}"
    )
