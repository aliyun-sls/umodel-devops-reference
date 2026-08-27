"""Adapter factory: instantiate adapters by provider type name."""

import logging
from typing import Any, Dict

from .base import IGitAdapter
from .deploy_base import IDeployAdapter

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = ("gitlab", "codeup")
_SUPPORTED_DEPLOY_PROVIDERS = ("argocd",)


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


def create_deploy_adapter(provider_type: str, config: Dict[str, Any]) -> IDeployAdapter:
    """Return an IDeployAdapter implementation for ``provider_type``.

    Supported values:
        - "argocd" → ArgoCDAdapter (Argo CD REST API)
    """
    provider_type = (provider_type or "").lower()
    if provider_type == "argocd":
        from .argocd.adapter import ArgoCDAdapter

        return ArgoCDAdapter(config)
    raise ValueError(
        f"Unsupported deploy_provider type '{provider_type}'. "
        f"Supported: {_SUPPORTED_DEPLOY_PROVIDERS}"
    )
