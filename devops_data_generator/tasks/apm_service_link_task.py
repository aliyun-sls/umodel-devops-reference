"""apm_service_sourced_from_repository relationship task.

Links an APM service (CMS-native entity, `apm.service`) to the DevOps
repository its code lives in — the RCA entry edge ("which repo is behind
this alerting service").

Why dynamic resolution instead of the static_topo template: the apm.service
entity id is computed by CMS (opaque md5 — same lesson as k8s.pod, see
remote memory umodel-k8s-pod-id-divergence). We cannot recompute it, so we
READ the current id from the workspace `__entity` logstore each cycle and
reference it verbatim. The repository side goes through the normal
enrich path (md5 of the raw repository_id, aligned with the node id).

Config (app_config.yaml):

    apm_service_link:
      links:
        - service: "sae-order-processor"   # apm.service 的 service 字段（精确匹配）
          repository_id: "7069710"          # devops.repository 的原始主键

Reads the SLS ``__entity`` logstore (sls: section credentials) instead of
the CMS graph API: apm.service entities are rewritten only on change
(keep-alive ~5y), so a graph-window query could miss them, while the raw
logstore always has the latest row until TTL (30d).

Missing service / no rows → no edge (没有边优于错误边).
"""

import logging
import time
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)

# SLS SDK optional (same pattern as other cloud-dependent tasks)
try:
    from aliyun.log import LogClient, GetLogsRequest
    SLS_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    LogClient = None
    GetLogsRequest = None
    SLS_SDK_AVAILABLE = False

ALLOWED_SERVICE_CHARS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
LOOKBACK_SECONDS = 7 * 86400  # apm.service 写入稀疏（变更才写），窗口放宽到 7 天


class ApmServiceSourcedFromRepositoryTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"
        self.task_name = "apm_service_sourced_from_repository"
        self.links = config.get("links") or []
        self.sls_config = config.get("sls") or {}

    def get_dependencies(self) -> List[str]:
        return ["repository"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        services = self._load_apm_services()
        if not services:
            logger.warning("apm_service_link: no apm.service rows found in workspace")
            return []

        relationships: List[Dict[str, Any]] = []
        for link in self.links:
            service = (link.get("service") or "").strip()
            repository_id = str(link.get("repository_id") or "").strip()
            if not service or not repository_id:
                continue
            entity_id = services.get(service)
            if not entity_id:
                logger.warning("apm_service_link: service %r not found in workspace; no edge", service)
                continue
            relationships.append({
                "__link_type__": "sourced_from",
                "__src_entity_id__": entity_id,       # CMS 侧 id 原样引用（不重算）
                "__dest_entity_id__": repository_id,  # enrich 会用主键 md5 覆盖对齐
                "entity_id": entity_id,               # 供 enrich 的 src_use_field 读取
                "repository_id": repository_id,       # 供 enrich 的 dest md5
                "service": service,
            })

        self.set_shared_data(
            "apm_service_sourced_from_repository_list", relationships, "relationship_data")
        logger.info("Generated %s apm_service_sourced_from_repository relationships",
                    len(relationships))
        return relationships

    def validate_config(self) -> bool:
        if not SLS_SDK_AVAILABLE:
            logger.warning("aliyun-log SDK not installed")
            return False
        return bool(self.links)

    # ---- internals ---------------------------------------------------------

    def _load_apm_services(self) -> Dict[str, str]:
        """service name → latest __entity_id__, from the workspace __entity logstore."""
        client = LogClient(
            self.sls_config.get("endpoint", ""),
            self.sls_config.get("access_key_id", ""),
            self.sls_config.get("access_key_secret", ""),
        )
        project = self.sls_config.get("project", "")
        logstore = self.sls_config.get("entity_logstore", "")
        to = int(time.time())
        req = GetLogsRequest(
            project=project, logstore=logstore,
            fromTime=to - LOOKBACK_SECONDS, toTime=to,
            query='__entity_type__:"apm.service"', line=1000, offset=0, reverse=True,
        )
        rows = [lg.get_contents() for lg in client.get_logs(req).get_logs()]
        latest: Dict[str, Any] = {}
        for row in rows:
            name = row.get("service", "")
            ts = row.get("__last_observed_time__", "") or "0"
            eid = row.get("__entity_id__", "")
            if name and eid and (name not in latest or str(ts) > str(latest[name][0])):
                latest[name] = (ts, eid)
        return {name: eid for name, (ts, eid) in latest.items()}
