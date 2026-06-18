#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pod uses docker_image relationship task.

Builds the k8s.pod_uses_devops.docker_image relation from Kubernetes pod
container specs and docker_image records. Depends on kubernetes_pod +
docker_image.
"""

import hashlib
import logging
from typing import Dict, List, Any

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class PodUsesDockerImageTask(BaseTask):
    """Generate k8s.pod_uses_devops.docker_image relations."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"
        logger.info("PodUsesDockerImageTask initialized")

    def get_dependencies(self) -> List[str]:
        return ["kubernetes_pod", "docker_image"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        try:
            pods = self.get_shared_data("k8s_pod_raw_data", [])
            images = self.get_shared_data("docker_image_raw_data", [])
            if not pods:
                logger.warning("No pod data found in shared context")
                return []
            if not images:
                logger.warning("No docker_image data found in shared context")
                return []

            image_lookup = self._build_image_lookup(images)
            relationships: List[Dict[str, Any]] = []

            for pod in pods:
                pod_images = pod.get("images", [])
                pod_id = pod.get("pod_id", "")
                if not pod_images or not pod_id:
                    continue
                for container_image in pod_images:
                    matching_image = self._find_matching_image(container_image, image_lookup)
                    if matching_image:
                        relationship = self._create_relationship(pod, matching_image, container_image)
                        if relationship:
                            relationships.append(relationship)

            self.set_shared_data("pod_uses_docker_image_list", relationships, "relationship_data")
            logger.info("Generated %s pod_uses_docker_image relationships", len(relationships))
            return relationships
        except Exception as e:
            error_msg = f"Error generating pod-docker_image relationships: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _build_image_lookup(self, images: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        image_lookup: Dict[str, Dict[str, Any]] = {}
        for image in images:
            repository = image.get("repository", "") or ""
            tag = image.get("tag", "") or ""
            full_image_name = image.get("full_image_name", "") or ""
            if not repository and not full_image_name:
                continue
            identifiers: List[str] = []
            if tag:
                if full_image_name:
                    identifiers.append(f"{full_image_name}")
                if repository:
                    identifiers.append(f"{repository}:{tag}")
                    identifiers.append(f"{repository.split('/')[-1]}:{tag}")
            if full_image_name:
                identifiers.append(full_image_name)
            if repository:
                identifiers.append(repository)
                identifiers.append(repository.split('/')[-1])
            for identifier in identifiers:
                if identifier:
                    image_lookup[identifier] = image
        return image_lookup

    def _find_matching_image(self, container_image: str, image_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        if not container_image:
            return None
        possible_matches = [
            container_image,
            container_image.split('/')[-1] if '/' in container_image else container_image,
            container_image.split(':')[0] if ':' in container_image else None,
            container_image.split('/')[-1].split(':')[0] if ('/' in container_image and ':' in container_image) else None,
        ]
        possible_matches = [m for m in possible_matches if m]
        for match_key in possible_matches:
            if match_key in image_lookup:
                return image_lookup[match_key]
        # Fuzzy fallback on image-name stem.
        container_stem = self._image_stem(container_image)
        for lookup_key, image in image_lookup.items():
            if container_stem and self._image_stem(lookup_key) == container_stem:
                return image
        return None

    @staticmethod
    def _image_stem(full_image: str) -> str:
        if not full_image:
            return ""
        return full_image.split(":")[0].split("/")[-1]

    def _create_relationship(self, pod: Dict[str, Any], image: Dict[str, Any], container_image: str) -> Dict[str, Any]:
        try:
            pod_entity_id = pod.get("entity_id", pod.get("pod_id", ""))
            image_entity_id = image.get("docker_image_id", "") or self._generate_entity_id(image, "docker_image")
            return {
                "__relation_type__": "uses",
                "__link_type__": "uses",
                "__src_domain__": "k8s",
                "__src_entity_type__": "k8s.pod",
                "__src_entity_id__": pod_entity_id,
                "__dest_domain__": "devops",
                "__dest_entity_type__": "devops.docker_image",
                "__dest_entity_id__": image_entity_id,
                "pod_id": pod.get("pod_id", ""),
                "docker_image_id": image.get("docker_image_id", ""),
                "repository": image.get("repository", ""),
                "tag": image.get("tag", ""),
                "container_image": container_image,
                "namespace": pod.get("namespace", ""),
                "container_count": pod.get("container_count", 0),
                "priority": 5,
                "relationship_source": "container_spec",
                "uses_type": "container_runtime",
            }
        except Exception as e:  # noqa: BLE001
            logger.error("Error creating relationship: %s", e)
            return {}

    def _generate_entity_id(self, entity: Dict[str, Any], entity_type: str) -> str:
        primary_keys_map = {"docker_image": ["docker_image_id"], "pod": ["pod_id"]}
        primary_keys = primary_keys_map.get(entity_type, ["id"])
        values = [str(entity.get(k, "")) for k in primary_keys]
        joined = "|".join(values)
        if joined:
            return hashlib.md5(joined.encode("utf-8")).hexdigest()
        return str(entity.get("entity_id", entity.get("id", "")))

    def validate_config(self) -> bool:
        return True

    def get_task_name(self) -> str:
        return "pod_uses_docker_image"
