"""release_contains_artifact relationship task.

release → artifact (contains). A release is linked to an artifact when their
tag names match. To prevent cross-linking between different repositories that
happen to share a tag name (e.g. both have ``v1.0.0``), matching is scoped by
the repo→registry mapping in ``repo_image_mapping.yaml``: when a release's
source repository maps to an ACR registry, only artifacts in that registry
are considered. When no mapping is configured, matching falls back to tag-only
(per-tag, the historical behaviour). Depends on release + docker_image.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class ReleaseContainsArtifactTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"

    def get_dependencies(self) -> List[str]:
        return ["release", "docker_image"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        releases = self.get_shared_data("release_list", [])
        artifacts = self.get_shared_data("artifact_raw_data", [])
        if not releases or not artifacts:
            logger.warning("release_contains_artifact: missing release or artifact data")
            return []

        # repo path → ACR registry mapping (repo_image_mapping.yaml). When a
        # release's source repo maps to a registry, tag matching is scoped to
        # that registry so two repos sharing a tag no longer cross-link.
        repo_registry_map = self._load_repo_registry_mapping()
        repo_path_by_id = {
            str(repo.get("repository_id", "")): repo.get("full_path", "")
            for repo in (self.get_shared_data("repository_raw_data", []) or [])
            if repo.get("repository_id")
        }

        # Index artifacts by tag_name; keep registry for scoped matching.
        by_tag: Dict[str, List[Dict[str, Any]]] = {}
        for art in artifacts:
            tag = art.get("tag_name", "")
            if tag:
                by_tag.setdefault(tag, []).append(art)

        relationships: List[Dict[str, Any]] = []
        for release in releases:
            tag_name = release.get("tag_name", "")
            release_id = release.get("release_id", "")
            if not tag_name or not release_id:
                continue
            target_registry = repo_registry_map.get(
                repo_path_by_id.get(str(release.get("repository_id", "")), "")
            )
            for art in by_tag.get(tag_name, []):
                # Scope by registry when a mapping exists; otherwise fall back
                # to tag-only matching (historical behaviour for unmapped repos).
                if target_registry:
                    art_registry = str(art.get("registry", "") or "")
                    if not (
                        art_registry == target_registry
                        or target_registry in art_registry
                        or art_registry in target_registry
                    ):
                        continue
                artifact_id = art.get("artifact_id", "")
                if not artifact_id:
                    continue
                relationships.append(
                    {
                        "__link_type__": "contains",
                        "__src_entity_id__": release_id,
                        "__dest_entity_id__": artifact_id,
                        "release_id": release_id,
                        "artifact_id": artifact_id,
                        "tag_name": tag_name,
                    }
                )

        self.set_shared_data("release_contains_artifact_list", relationships, "relationship_data")
        logger.info("Generated %s release_contains_artifact relationships", len(relationships))
        return relationships

    # repo_image_mapping.yaml lives in devops_data_generator/config/.
    _MAPPING_FILE = Path(__file__).resolve().parent.parent / "config" / "repo_image_mapping.yaml"

    def _load_repo_registry_mapping(self) -> Dict[str, str]:
        """Load ``repo_image_mappings`` from repo_image_mapping.yaml (best-effort).

        Returns git repo path → ACR registry. A missing or template-only file
        yields an empty dict, in which case tag matching falls back to the
        global (per-tag) behaviour. Placeholder template values such as
        ``<GIT_REPO_PATH>`` are ignored.
        """
        try:
            import yaml  # soft import: PyYAML is a runtime dep of config_loader
        except ImportError:  # pragma: no cover
            logger.warning("PyYAML not installed; repo_image_mapping.yaml disabled")
            return {}
        try:
            if not self._MAPPING_FILE.exists():
                logger.debug("repo_image_mapping.yaml not found at %s", self._MAPPING_FILE)
                return {}
            with open(self._MAPPING_FILE, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            mappings = data.get("repo_image_mappings") or {}
            cleaned: Dict[str, str] = {}
            for repo_path, registry in mappings.items():
                rp = str(repo_path or "")
                rg = str(registry or "")
                if (
                    rp
                    and rg
                    and not (rp.startswith("<") and rp.endswith(">"))
                    and not (rg.startswith("<") and rg.endswith(">"))
                ):
                    cleaned[rp] = rg
            if cleaned:
                logger.info("Loaded %s repo→registry mappings from repo_image_mapping.yaml", len(cleaned))
            return cleaned
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load repo_image_mapping.yaml: %s", exc)
            return {}

    def validate_config(self) -> bool:
        return True
