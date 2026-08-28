#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Yunxiao Flow adapter — maps Yunxiao Flow pipelines/runs into the unified CI
schemas (see adapters/ci_base.py for the contract).

Reads via the Yunxiao standard REST API (stdlib urllib, no SDK):
  - GET {endpoint}/oapi/v1/flow/organizations/{org}/pipelines            → definitions
  - GET {endpoint}/oapi/v1/flow/organizations/{org}/pipelines/{id}/runs  → executions
  - GET {...}/pipelines/{id}/runs/{runId}                                → run detail (sources)

Auth: personal access token (PAT, ``pt-...``) in the ``x-yunxiao-token``
header. RAM AK/SK cannot call Flow APIs for accounts that never logged into
the Yunxiao console (org-role grants don't provision the Flow-side account),
so PAT is the only workable credential for service accounts.

Config (app_config.yaml section ``yunxiao_flow``):
  organization_id: "<云效组织ID>"
  personal_access_token: "<pt-...>"   # 云效个人访问令牌（流水线读权限）
  endpoint: ""                        # default https://openapi-rdc.aliyuncs.com
  repo_mapping:                       # optional: pipeline name → git repository_id
    "demo-deploy-hk": "90001"
  max_runs_per_pipeline: 20           # recent runs collected per pipeline
  fetch_run_detail: false             # per-run detail call to fill commit_sha/
                                      # branch/repository_id from job sources (N+1)

Field notes (observed from the live API):
  - ListPipelines returns a bare JSON array (no total); paginate until a short page.
  - ListPipelineRuns item: {pipelineRunId, pipelineId, status, startTime,
    endTime, triggerMode, creatorAccountId}. status ∈ SUCCESS/RUNNING/FAIL/
    CANCELED/WAITING; triggerMode: 1 manual, 2 schedule, 3 push, 5 pipeline,
    6 webhook.
  - Run detail carries job ``params`` (JSON string) whose ``sources[0].data``
    has commitId/branch/projectId/repo for Codeup-sourced pipelines — the
    run → commit/repository link.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..ci_base import ICIAdapter

logger = logging.getLogger(__name__)

PROVIDER_NAME = "yunxiao_flow"

DEFAULT_ENDPOINT = "https://openapi-rdc.aliyuncs.com"
_PER_PAGE = 30  # API maximum

_RUN_STATUS_MAP = {
    "SUCCESS": ("success", "success"),
    "FAIL": ("failure", "failure"),
    "RUNNING": ("in_progress", ""),
    "CANCELED": ("cancelled", "cancelled"),
    "WAITING": ("queued", ""),
}

_TRIGGER_MODE_MAP = {
    1: "manual",
    2: "schedule",
    3: "push",
    5: "pipeline",   # triggered by another pipeline
    6: "webhook",
}


class YunxiaoFlowAdapter(ICIAdapter):
    """ICIAdapter implementation backed by the Yunxiao standard REST API."""

    def __init__(self, config: Dict[str, Any]):
        self.organization_id = config.get("organization_id") or ""
        self.token = config.get("personal_access_token") or ""
        self.endpoint = (config.get("endpoint") or DEFAULT_ENDPOINT).rstrip("/")
        self.repo_mapping = dict(config.get("repo_mapping") or {})
        self.max_runs_per_pipeline = int(config.get("max_runs_per_pipeline") or 20)
        self.fetch_run_detail = bool(config.get("fetch_run_detail", False))

    # ---- ICIAdapter ---------------------------------------------------

    def get_provider_name(self) -> str:
        return PROVIDER_NAME

    def validate_config(self) -> bool:
        if not self.organization_id:
            logger.error("yunxiao_flow.organization_id is required")
            return False
        if not self.token:
            logger.error("yunxiao_flow.personal_access_token is required")
            return False
        try:
            self._get(f"/oapi/v1/flow/organizations/{self.organization_id}"
                      f"/pipelines?page=1&perPage=1")
            return True
        except Exception as e:
            logger.error("yunxiao_flow validate_config failed: %s", e)
            return False

    def list_pipelines(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for item in self._paginate(f"/oapi/v1/flow/organizations/"
                                   f"{self.organization_id}/pipelines"):
            pid = item.get("pipelineId")
            name = item.get("pipelineName") or ""
            if pid is None:
                continue
            out.append({
                "pipeline_id": f"{PROVIDER_NAME}:{pid}",
                "repository_id": self.repo_mapping.get(name, ""),
                "name": name,
                "file_path": "",          # Flow pipelines are console-orchestrated
                "description": "",
                "data_source": PROVIDER_NAME,
                "platform_pipeline_id": str(pid),
                "url": self._pipeline_url(pid),
                "is_active": True,
                "created_at": self._iso(item.get("createTime")),
                "updated_at": "",
            })
        return out

    def list_pipeline_runs(self) -> List[Dict[str, Any]]:
        runs: List[Dict[str, Any]] = []
        for pipe in self.list_pipelines():
            pid = pipe["platform_pipeline_id"]
            items = self._paginate(
                f"/oapi/v1/flow/organizations/{self.organization_id}"
                f"/pipelines/{pid}/runs",
                limit=self.max_runs_per_pipeline)
            for item in items:
                detail = None
                if self.fetch_run_detail:
                    try:
                        detail = self._get(
                            f"/oapi/v1/flow/organizations/{self.organization_id}"
                            f"/pipelines/{pid}/runs/{item.get('pipelineRunId')}")
                    except Exception as e:  # noqa: BLE001
                        logger.warning("yunxiao_flow run detail %s/%s failed: %s",
                                       pid, item.get("pipelineRunId"), e)
                runs.append(self._map_run(pipe, item, detail))
        logger.info("yunxiao_flow: produced %s pipeline_run records", len(runs))
        return runs

    # ---- mapping -------------------------------------------------------

    def _map_run(self, pipe: Dict[str, Any], item: Dict[str, Any],
                 detail: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        pid = pipe["platform_pipeline_id"]
        rid = item.get("pipelineRunId")
        status, conclusion = _RUN_STATUS_MAP.get(
            (item.get("status") or "").upper(), ("queued", ""))
        start_ms = item.get("startTime") or 0
        end_ms = item.get("endTime") or 0

        commit_sha, branch, repository_id = "", "", pipe["repository_id"]
        if detail:
            source = self._extract_source(detail)
            if source:
                commit_sha = source.get("commitId") or ""
                branch = source.get("branch") or ""
                project_id = source.get("projectId")
                if project_id:
                    repository_id = str(project_id)

        return {
            "run_id": f"{PROVIDER_NAME}:{pid}:{rid}",
            "pipeline_id": pipe["pipeline_id"],
            "repository_id": repository_id,
            "number": rid or 0,
            "pr_id": "",
            "commit_sha": commit_sha,
            "branch": branch,
            "trigger_type": _TRIGGER_MODE_MAP.get(item.get("triggerMode"), "manual"),
            "status": status,
            "conclusion": conclusion,
            "data_source": PROVIDER_NAME,
            "platform_run_id": str(rid),
            "url": pipe["url"],
            "triggered_by": item.get("creatorAccountId") or "",
            "stages": "",
            "created_at": self._iso(start_ms),
            "started_at": self._iso(start_ms),
            "completed_at": self._iso(end_ms) if end_ms else "",
            "duration_seconds": int((end_ms - start_ms) / 1000) if end_ms and start_ms else 0,
            "queue_duration_seconds": 0,
        }

    @staticmethod
    def _extract_source(detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Pull the first code source out of run-detail job params.

        Detail shape: stages[].stageInfo.jobs[].params (JSON string)
        → sources[].data = {commitId, branch, projectId, repo, type, ...}.
        """
        for stage in (detail.get("stages") or []):
            jobs = ((stage or {}).get("stageInfo") or {}).get("jobs") or []
            for job in jobs:
                raw = (job or {}).get("params")
                if not raw:
                    continue
                try:
                    params = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                for source in (params.get("sources") or []):
                    if not isinstance(source, dict):
                        continue
                    data = source.get("data") or {}
                    if not isinstance(data, dict):
                        continue
                    if data.get("commitId") or data.get("projectId"):
                        return data
        return None

    @staticmethod
    def _pipeline_url(pid: Any) -> str:
        return f"https://flow.aliyun.com/pipelines/{pid}/current"

    @staticmethod
    def _iso(ts_ms: Any) -> str:
        if not ts_ms:
            return ""
        return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).isoformat()

    # ---- HTTP ------------------------------------------------------------

    def _paginate(self, path: str, limit: int = 0) -> List[Dict[str, Any]]:
        """Follow page/perPage pagination until a short page (or ``limit``)."""
        sep = "&" if "?" in path else "?"
        out: List[Dict[str, Any]] = []
        page = 1
        while True:
            batch = self._get(f"{path}{sep}page={page}&perPage={_PER_PAGE}")
            if not isinstance(batch, list):
                logger.warning("yunxiao_flow: unexpected payload at %s page %s: %r",
                               path, page, str(batch)[:120])
                break
            out.extend(b for b in batch if isinstance(b, dict))
            if len(batch) < _PER_PAGE or (limit and len(out) >= limit):
                break
            page += 1
        return out[:limit] if limit else out

    def _get(self, path: str) -> Any:
        req = urllib.request.Request(f"{self.endpoint}{path}")
        req.add_header("x-yunxiao-token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"yunxiao_flow GET {path} → HTTP {e.code}: "
                f"{e.read().decode('utf-8', 'replace')[:200]}")
