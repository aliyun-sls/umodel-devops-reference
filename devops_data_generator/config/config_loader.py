import logging
import os
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)


class ConfigLoader:
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_dir = config_dir
        self.app_config = self._load_yaml_file(os.path.join(config_dir, "app_config.yaml"))
        self.mapping_config = self._load_yaml_file(os.path.join(config_dir, "data_mapping.yaml"))
        logger.info("Configuration loaded successfully")

    def _load_yaml_file(self, file_path: str) -> Dict[str, Any]:
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                return yaml.safe_load(handle) or {}
        except FileNotFoundError:
            logger.error("Config file not found: %s", file_path)
            return {}
        except Exception as exc:
            logger.error("Error loading config file %s: %s", file_path, exc)
            return {}

    # ------------------------------------------------------------------
    # Git provider selection (new in v0.1)
    # ------------------------------------------------------------------
    def get_git_provider_type(self) -> str:
        """Return the active git provider type.

        Reads ``app_config['git_provider']['type']`` and falls back to
        ``"gitlab"`` so legacy configs without the new block keep
        working.
        """
        return self.app_config.get("git_provider", {}).get("type", "gitlab") or "gitlab"

    def get_git_provider_config(self) -> Dict[str, Any]:
        """Return the provider-specific config block.

        ``gitlab`` → ``app_config['gitlab']`` (url / access_token / ...)
        ``codeup`` → ``app_config['codeup']`` (organization_id / ak/sk / ...)
        """
        provider_type = self.get_git_provider_type()
        return self.app_config.get(provider_type, {}) or {}

    # ------------------------------------------------------------------
    # Legacy accessors (still used by callers that have not been migrated)
    # ------------------------------------------------------------------
    def get_gitlab_config(self) -> Dict[str, Any]:
        return self.app_config.get("gitlab", {})

    def get_codeup_config(self) -> Dict[str, Any]:
        return self.app_config.get("codeup", {})

    def get_sls_config(self) -> Dict[str, Any]:
        return self.app_config.get("sls", {})

    def get_tasks_config(self) -> Dict[str, Any]:
        return self.app_config.get("tasks", {})

    def get_logging_config(self) -> Dict[str, Any]:
        return self.app_config.get("logging", {})

    def get_acr_config(self) -> Dict[str, Any]:
        return self.app_config.get("acr", {})

    def get_cms_config(self) -> Dict[str, Any]:
        return self.app_config.get("cms", {})

    def get_kubernetes_config(self) -> Dict[str, Any]:
        return self.app_config.get("kubernetes", {})

    def get_data_mapping_config(self) -> Dict[str, Any]:
        return self.mapping_config

    def get_entity_config(self, entity_type: str) -> Dict[str, Any]:
        return self.mapping_config.get("entity", {}).get(entity_type, {})

    def get_relationship_config(self, relationship_type: str) -> Dict[str, Any]:
        return self.mapping_config.get("topo", {}).get(relationship_type, {})

    def resolve_config_path(self, filename: str) -> str:
        return os.path.join(self.config_dir, filename)

    def validate_config(self) -> bool:
        """Validate config based on active git provider.

        GitLab requires ``url + access_token``; codeup requires
        ``organization_id + access_key_id + access_key_secret``.
        """
        provider = self.get_git_provider_type()
        provider_config = self.get_git_provider_config()

        if provider == "gitlab":
            if not provider_config.get("url") or not provider_config.get("access_token"):
                logger.error("Missing GitLab url/access_token under app_config['gitlab']")
                return False
        elif provider == "codeup":
            missing = [
                key
                for key in ("organization_id", "access_key_id", "access_key_secret")
                if not provider_config.get(key)
            ]
            if missing:
                logger.error("Missing codeup config keys under app_config['codeup']: %s", missing)
                return False
        else:
            logger.error("Unsupported git_provider type: %s", provider)
            return False

        sls_config = self.get_sls_config()
        if not sls_config.get("endpoint") or not sls_config.get("project"):
            logger.error("Missing SLS configuration")
            return False

        if not self.mapping_config.get("entity"):
            logger.error("Missing entity configuration")
            return False

        return True
