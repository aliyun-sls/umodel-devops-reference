"""Deployment Task — fetch deployment facts via IDeployAdapter.list_deployments.

Produces ``devops.deployment`` entity records from CD systems (Argo CD,
GitLab CD, …). Multiple deploy adapters merge into this single task — the
same multi-source pattern as the CI pipeline tasks — so e.g. GitLab CD and
Argo CD can feed the graph side by side; one failing source does not sink
the others.

Emits ``release_relates_to_deployment`` edges when a deployment's commit_sha
matches a known release's target_commitish/tag_name (shared release data).
"""

import logging
from typing import Any, Dict, List, Optional

from adapters import IDeployAdapter
from .base_task import BaseTask

logger = logging.getLogger(__name__)


class DeploymentTask(BaseTask):
    """Deployment task — provider-agnostic, merges all deploy adapters."""

    def __init__(self, config: Dict[str, Any],
                 deploy_adapters: Optional[List[IDeployAdapter]] = None):
        super().__init__(config)
        self.deploy_adapters = deploy_adapters or []

    def get_dependencies(self) -> List[str]:
        # release data is optional but preferred (for release↔deployment edges)
        return ["release"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        deployments: List[Dict[str, Any]] = []
        for adapter in self.deploy_adapters:
            try:
                records = adapter.list_deployments()
            except Exception as exc:  # noqa: BLE001 — one failing CD source
                logger.warning(  # must not sink the other sources
                    "Failed to fetch deployments from %s: %s",
                    adapter.get_provider_name(), exc,
                )
                continue
            for d in records:
                self.set_shared_data(
                    f"deployment_{d.get('deployment_id', '')}", d, "deployment"
                )
            deployments.extend(records)
        logger.info(
            "Fetched %s deployments from %s deploy adapter(s)",
            len(deployments),
            len(self.deploy_adapters),
        )
        return deployments

    def validate_config(self) -> bool:
        ok = bool(self.deploy_adapters)
        for adapter in self.deploy_adapters:
            ok = adapter.validate_config() and ok
        return ok
