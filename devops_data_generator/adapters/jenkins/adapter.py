#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jenkins adapter — maps Jenkins jobs/builds into the unified CI schemas
(see adapters/ci_base.py for the contract).

Reads via Jenkins REST API (stdlib urllib, no extra dependency):
  - GET {url}/api/json?tree=jobs[name,url,buildable]            → definitions
  - GET {url}/job/{name}/api/json?tree=builds[...]              → executions

Config (app_config.yaml section ``jenkins``):
  url: "http://172.16.0.191:8081"     # Jenkins base URL (no trailing /)
  user: "admin"                       # 用户名
  token: "<api token or password>"    # API token（推荐）或密码
  job_filter: []                      # 可选：job 白名单
  repo_mapping:                       # 可选：job 名 → git repository_id（归一边用）
    "demo-app-build": "1"

Jenkins freestyle jobs carry no VCS info; commit_sha/branch are "" unless the
job is SCM-backed (then a future revision can read lastBuild revision).
"""

import base64
import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from ..ci_base import ICIAdapter

logger = logging.getLogger(__name__)

PROVIDER_NAME = "jenkins"


class JenkinsAdapter(ICIAdapter):
    """ICIAdapter implementation backed by Jenkins REST API."""

    def __init__(self, config: Dict[str, Any]):
        self.url = (config.get("url") or "").rstrip("/")
        self.user = config.get("user") or ""
        self.token = config.get("token") or ""
        self.insecure = bool(config.get("insecure", True))
        self.job_filter = set(config.get("job_filter") or [])
        self.repo_mapping = dict(config.get("repo_mapping") or {})

    # ---- ICIAdapter ---------------------------------------------------

    def get_provider_name(self) -> str:
        return PROVIDER_NAME

    def validate_config(self) -> bool:
        if not self.url:
            logger.error("jenkins.url is required")
            return False
        try:
            self._get("/api/json?tree=mode")
            return True
        except Exception as e:
            logger.error("jenkins validate_config failed: %s", e)
            return False

    def list_pipelines(self) -> List[Dict[str, Any]]:
        data = self._get("/api/json?tree=jobs[name,url,buildable]")
        out: List[Dict[str, Any]] = []
        for job in (data.get("jobs") or []):
            name = job.get("name", "")
            if not name or (self.job_filter and name not in self.job_filter):
                continue
            out.append({
                "pipeline_id": f"{PROVIDER_NAME}:{name}",
                "repository_id": self.repo_mapping.get(name, ""),
                "name": name,
                "file_path": "",          # freestyle 无配置文件概念
                "description": "",
                "data_source": PROVIDER_NAME,
                "platform_pipeline_id": name,
                "url": job.get("url", ""),
                "is_active": bool(job.get("buildable", True)),
                "created_at": "",
                "updated_at": "",
            })
        return out

    def list_pipeline_runs(self) -> List[Dict[str, Any]]:
        runs: List[Dict[str, Any]] = []
        for pipe in self.list_pipelines():
            name = pipe["platform_pipeline_id"]
            tree = ("builds[number,result,duration,timestamp,url,"
                    "building,estimatedDuration,queueId]{0,20}")
            data = self._get(f"/job/{urllib.parse.quote(name)}/api/json?tree={tree}")
            for b in (data.get("builds") or []):
                runs.append(self._map_build(name, pipe, b))
        logger.info("jenkins: produced %s pipeline_run records", len(runs))
        return runs

    # ---- mapping -------------------------------------------------------

    def _map_build(self, job: str, pipe: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        number = b.get("number", 0)
        building = bool(b.get("building", False))
        result = b.get("result")  # SUCCESS/FAILURE/ABORTED/None(building)
        status, conclusion = self._derive_status(building, result)
        ts_ms = b.get("timestamp") or 0
        duration_s = int((b.get("duration") or 0) / 1000)
        return {
            "run_id": f"{PROVIDER_NAME}:{job}:{number}",
            "pipeline_id": pipe["pipeline_id"],
            "repository_id": pipe["repository_id"],
            "number": number,
            "pr_id": "",
            "commit_sha": "",
            "branch": "",
            "trigger_type": "manual",
            "status": status,
            "conclusion": conclusion,
            "data_source": PROVIDER_NAME,
            "platform_run_id": str(number),
            "url": b.get("url", ""),
            "triggered_by": "jenkins",
            "stages": "",
            "created_at": self._iso(ts_ms),
            "started_at": self._iso(ts_ms),
            "completed_at": self._iso(ts_ms + (b.get("duration") or 0)) if not building else "",
            "duration_seconds": duration_s,
            "queue_duration_seconds": 0,
        }

    @staticmethod
    def _derive_status(building: bool, result: Optional[str]):
        if building:
            return "in_progress", ""
        return {
            "SUCCESS": ("success", "success"),
            "FAILURE": ("failure", "failure"),
            "ABORTED": ("cancelled", "cancelled"),
            "UNSTABLE": ("success", ""),   # 构建成但测试不净：run 成功、无 conclusion
            "NOT_BUILT": ("skipped", ""),
        }.get(result or "", ("queued", ""))

    @staticmethod
    def _iso(ts_ms: int) -> str:
        if not ts_ms:
            return ""
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()

    # ---- HTTP ------------------------------------------------------------

    def _get(self, path: str) -> Dict[str, Any]:
        req = urllib.request.Request(f"{self.url}{path}")
        if self.user and self.token:
            auth = base64.b64encode(f"{self.user}:{self.token}".encode()).decode()
            req.add_header("Authorization", f"Basic {auth}")
        ctx = None
        if self.insecure and self.url.startswith("https"):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"jenkins GET {path} → HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")
