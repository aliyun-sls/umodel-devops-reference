"""Deployment Task — fetch deployment facts via IDeployAdapter.list_deployments.

Produces ``devops.deployment`` entity records from CD systems (Argo CD, …).
Emits ``release_relates_to_deployment`` edges when a deployment's commit_sha
matches a known release's target_commitish/tag_name (shared release data).
"""

import logging
from typing import Any, Dict, List

from adapters import IDeployAdapter
from .base_task import BaseTask

logger = logging.getLogger(__name__)


class DeploymentTask(BaseTask):
    """Deployment task — provider-agnostic, delegates to deploy_adapter."""

    def __init__(self, config: Dict[str, Any], deploy_adapter: IDeployAdapter):
        super().__init__(config)
        self.deploy_adapter = deploy_adapter

    def get_dependencies(self) -> List[str]:
        # release data is optional but preferred (for release↔deployment edges)
        return ["release"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        deployments = self.deploy_adapter.list_deployments()
        for d in deployments:
            self.set_shared_data(
                f"deployment_{d.get('deployment_id', '')}", d, "deployment"
            )
        logger.info(
            "Fetched %s deployments via %s adapter",
            len(deployments),
            self.deploy_adapter.get_provider_name(),
        )
        return deployments

    def validate_config(self) -> bool:
        return self.deploy_adapter.validate_config()
