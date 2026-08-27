"""Deploy/CD adapter abstract base.

The deployment task calls into implementations of `IDeployAdapter`. Each
CD system (Argo CD / Yunxiao AppStack / ...) supplies its own subclass
mapping the provider-native API into the unified output schema documented
below.

This mirrors `adapters/base.py` (IGitAdapter) in style: the docstring is the
contract; subclasses only translate provider APIs into it.

Unified output schema
---------------------
``list_deployments()`` items (aligned with entity_set `devops.deployment`):
    {deployment_id, title, description, repository_id, run_id,
     environment_id, commit_sha, version, status, conclusion,
     data_source, platform_deployment_id, url, deployed_by, release_id,
     artifacts, created_at, started_at, completed_at, rollback_started_at,
     rollback_completed_at, duration_seconds}

Field semantics:
    deployment_id:       globally unique, stable across syncs of the same
                         deploy event, e.g. "argocd:{app}:{history_id}".
    repository_id:       the git repository entity id (GitLab numeric project
                         id as string) when resolvable via config mapping;
                         empty string when not resolvable.
    commit_sha:          the deployed source revision (git SHA).
    status:              one of queued/in_progress/success/failure/cancelled.
    conclusion:          one of success/failure/rolled_back (or "").
    data_source:         the literal from ``get_provider_name()``
                         (e.g. ``"argocd"``).
    platform_deployment_id: the provider-native id (e.g. Argo CD history id).
    environment_id:      destination identifier (e.g. "namespace" or
                         "cluster/namespace").
    created_at / started_at / completed_at: ISO 8601 strings or "" (never None).
    duration_seconds:    int; 0 when unknown.

``list_applications()`` items (for discovery/inspection):
    {name, repo_url, target_revision, dest_namespace, dest_server,
     sync_status, health_status}

Timestamps must be normalized to ISO 8601 with timezone (UTC preferred).
Providers must not raise on partial data: fill "" / 0 and keep going.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class IDeployAdapter(ABC):
    """Unified interface for CD/deploy systems (Argo CD, Yunxiao AppStack, ...)."""

    @abstractmethod
    def list_deployments(self) -> List[Dict[str, Any]]:
        """Return deployment records in the unified schema above."""

    @abstractmethod
    def list_applications(self) -> List[Dict[str, Any]]:
        """Return managed applications (discovery/inspection)."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Literal value written into the ``data_source`` field (e.g. ``"argocd"``)."""

    @abstractmethod
    def validate_config(self) -> bool:
        """Confirm credentials / endpoint / connectivity."""
