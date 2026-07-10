#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pod uses docker_image relationship task.

Builds the k8s.pod_uses_devops.docker_image relation from Kubernetes pod
container specs and docker_image records. Depends on kubernetes_pod +
docker_image.
"""

import hashlib
import logging
import re
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

            image_index = self._build_image_index(images)
            relationships: List[Dict[str, Any]] = []

            for pod in pods:
                pod_images = pod.get("images", [])
                pod_id = pod.get("pod_id", "")
                if not pod_images or not pod_id:
                    continue
                for container_image in pod_images:
                    matching_image = self._find_matching_image(container_image, image_index)
                    if matching_image:
                        relationship = self._create_relationship(pod, matching_image, container_image)
                        if relationship:
                            relationships.append(relationship)
                    else:
                        logger.info(
                            "pod %s image %s has no exact docker_image match "
                            "(ns+repo+tag/digest); no uses edge",
                            pod_id,
                            container_image,
                        )

            self.set_shared_data("pod_uses_docker_image_list", relationships, "relationship_data")
            logger.info("Generated %s pod_uses_docker_image relationships", len(relationships))
            return relationships
        except Exception as e:
            error_msg = f"Error generating pod-docker_image relationships: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    # No edge is better than a wrong edge: a wrong uses edge sends the trace
    # chain to the wrong artifact, release, and owner. The former repo-last-
    # segment fallback made o11y-demo/demo match otel-demo/demo, so matching is
    # now strict on full namespace, repository, and tag, with digest priority.
    _DIGEST_RE = re.compile(r'@?sha256:([0-9a-fA-F]{64})')

    # Alternate endpoints for the same ACR instance may be mapped to one value.
    # An empty map keeps host best-effort and identifies images by path and tag.
    REGISTRY_ALIASES = {
        # "o11y-demo-registry-vpc.cn-hongkong.cr.aliyuncs.com": "acr-instance",
        # "cri-yb40y6ac9o7xgej2.cn-hongkong.cr.aliyuncs.com": "acr-instance",
    }

    def _parse_image_ref(self, ref: str) -> Dict[str, Any]:
        """Parse an image ref into host, namespace, repo, tag, and digest."""
        if not ref:
            return None

        ref = ref.strip()
        if '://' in ref:
            ref = ref.split('://', 1)[1]

        digest = None
        digest_match = self._DIGEST_RE.search(ref)
        if digest_match:
            digest = digest_match.group(1).lower()
            ref = ref[:digest_match.start()] + ref[digest_match.end():]

        host = ''
        if '/' in ref:
            head = ref.split('/', 1)[0]
            if '.' in head or ':' in head:
                host, ref = head, ref.split('/', 1)[1]

        tag = 'latest'
        if ':' in ref:
            ref, tag = ref.rsplit(':', 1)

        parts = [part for part in ref.split('/') if part]
        if not parts:
            return None
        return {
            'host': host,
            'namespace': '/'.join(parts[:-1]),
            'repo': parts[-1],
            'tag': tag,
            'digest': digest,
        }

    def _normalize_host(self, host: str) -> str:
        if not host:
            return ''
        if host in self.REGISTRY_ALIASES:
            return self.REGISTRY_ALIASES[host]
        host = host.lower()
        return host[:-4] + '.' if host.endswith('-vpc.') else host

    def _build_image_index(self, images: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Index docker_image records by full namespace/repo/tag and digest."""
        by_path: Dict[tuple, Dict[str, Any]] = {}
        by_digest: Dict[str, Dict[str, Any]] = {}
        for image in images or []:
            if not isinstance(image, dict):
                continue
            repository = image.get('repository', '') or ''
            path_parts = [part for part in repository.split('/') if part]
            if not path_parts:
                continue

            key = (
                '/'.join(path_parts[:-1]),
                path_parts[-1],
                image.get('tag', '') or '',
            )
            by_path.setdefault(key, image)

            digest = (image.get('digest') or '').lower()
            digest_match = self._DIGEST_RE.search(digest)
            if digest_match:
                digest = digest_match.group(1).lower()
            if digest:
                by_digest.setdefault(digest, image)
        return {'by_path': by_path, 'by_digest': by_digest}

    def _find_matching_image(
        self,
        container_image: str,
        image_index: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return only an exact docker_image match; otherwise return None."""
        parsed = self._parse_image_ref(container_image)
        if not parsed:
            return None

        # A double-host path can be self-consistent with a malformed ACR
        # repository, but it is never a valid image namespace. Do not create
        # an edge to that garbage entity even when its path and tag match.
        namespace_segments = [
            segment for segment in parsed['namespace'].split('/') if segment
        ]
        if any('aliyuncs.com' in segment for segment in namespace_segments):
            logger.info(
                "rejecting malformed (double-host) image ref, no uses edge: %s",
                container_image,
            )
            return None

        if parsed['digest']:
            return image_index['by_digest'].get(parsed['digest'])

        key = (parsed['namespace'], parsed['repo'], parsed['tag'])
        candidate = image_index['by_path'].get(key)
        if not candidate:
            return None

        if self.REGISTRY_ALIASES and parsed['host']:
            candidate_ref = self._parse_image_ref(candidate.get('full_image_name', '') or '')
            candidate_host = self._normalize_host((candidate_ref or {}).get('host', ''))
            pod_host = self._normalize_host(parsed['host'])
            if candidate_host and pod_host and candidate_host != pod_host:
                logger.warning(
                    "pod image %s host %s != docker_image host %s (after alias); skipping edge",
                    container_image,
                    parsed['host'],
                    (candidate_ref or {}).get('host', ''),
                )
                return None

        return candidate

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
