#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Argo CD adapter — maps Argo CD Application sync history into the unified
deployment schema (see adapters/deploy_base.py for the contract).

Reads via Argo CD REST API (stdlib urllib, no extra dependency):
  - GET {server}/api/v1/applications               → app inventory
  - GET {server}/api/v1/applications/{name}        → status.history[] per app

Config (app_config.yaml section ``argocd``):
  server: "http://nlb-xxx:8080"        # Argo CD server base URL (no trailing /)
  token: "<bearer token>"              # API token; empty = fall back to login
  username: "" / password: ""          # optional; used to mint (and on 401,
                                       # re-mint) a session token — for
                                       # long-running producers, since session
                                       # tokens expire (default 24h)
  insecure: true                       # skip TLS verify for self-signed certs
  app_filter: []                       # optional allowlist of application names
  repo_mapping:                        # repoURL → GitLab project id（归一 repository_id）
    "http://nlb-xxx:8080/starops-demo/demo-app.git": "1"

Only git-sourced applications are considered (helm/oci-only apps are skipped,
they carry no commit sha).
"""

import json
import logging
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from ..deploy_base import IDeployAdapter

logger = logging.getLogger(__name__)

PROVIDER_NAME = "argocd"


class ArgoCDAdapter(IDeployAdapter):
    """IDeployAdapter implementation backed by Argo CD REST API."""

    def __init__(self, config: Dict[str, Any]):
        self.server = (config.get("server") or "").rstrip("/")
        self.token = config.get("token") or ""
        self.username = config.get("username") or ""
        self.password = config.get("password") or ""
        self.insecure = bool(config.get("insecure", True))
        self.app_filter = set(config.get("app_filter") or [])
        self.repo_mapping = dict(config.get("repo_mapping") or {})

    # ---- IDeployAdapter -------------------------------------------------

    def get_provider_name(self) -> str:
        return PROVIDER_NAME

    def validate_config(self) -> bool:
        if not self.server:
            logger.error("argocd.server is required")
            return False
        try:
            self._get("/api/v1/applications")
            return True
        except Exception as e:
            logger.error(f"argocd validate_config failed: {e}")
            return False

    def list_applications(self) -> List[Dict[str, Any]]:
        # NOTE: do NOT pass a `fields` projection — the gRPC-gateway field
        # mask silently drops metadata.name (observed on v3.5.1), breaking
        # every downstream per-app call. Fetch full objects instead.
        data = self._get("/api/v1/applications")
        out = []
        for item in (data.get("items") or []):
            meta = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})
            source = spec.get("source", {})
            dest = spec.get("destination", {})
            name = meta.get("name", "")
            if not name:
                logger.warning("argocd: skipping application with empty metadata.name")
                continue
            out.append({
                "name": name,
                "repo_url": source.get("repoURL", ""),
                "target_revision": source.get("targetRevision", ""),
                "dest_namespace": dest.get("namespace", ""),
                "dest_server": dest.get("server", ""),
                "sync_status": (status.get("sync") or {}).get("status", ""),
                "health_status": (status.get("health") or {}).get("status", ""),
            })
        return out

    def list_deployments(self) -> List[Dict[str, Any]]:
        deployments: List[Dict[str, Any]] = []
        for app in self.list_applications():
            name = app["name"]
            if self.app_filter and name not in self.app_filter:
                continue
            detail = self._get(f"/api/v1/applications/{name}")
            spec = detail.get("spec", {})
            status = detail.get("status", {})
            history = status.get("history") or []
            repo_url = (spec.get("source") or {}).get("repoURL", "")
            dest = spec.get("destination") or {}
            for h in history:
                rec = self._map_history(name, repo_url, dest, status, h)
                if rec:
                    deployments.append(rec)
        logger.info(f"argocd: produced {len(deployments)} deployment records")
        return deployments

    # ---- mapping ---------------------------------------------------------

    def _map_history(self, app: str, repo_url: str, dest: Dict[str, Any],
                     status: Dict[str, Any], h: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Map one Argo CD Application history entry to a deployment record.

        Returns None for non-git sources (helm/oci carry no commit sha).
        """
        revision = h.get("revision", "")
        if not revision:
            return None

        sync_status = (status.get("sync") or {}).get("status", "")
        health_status = (status.get("health") or {}).get("status", "")
        st, conclusion = self._derive_status(sync_status, health_status)

        started = h.get("deployStartedAt", "") or ""
        finished = h.get("deployedAt", "") or ""
        duration = self._duration_seconds(started, finished)

        hist_id = h.get("id", "")
        return {
            "deployment_id": f"argocd:{app}:{hist_id}",
            "title": f"argocd sync {app}@{revision[:8]}",
            "description": f"Argo CD application {app} sync #{hist_id} ({sync_status}/{health_status})",
            "repository_id": self.repo_mapping.get(repo_url, ""),
            "run_id": "",
            "environment_id": dest.get("namespace", "") or "",
            "commit_sha": revision,
            "version": revision[:8],
            "status": st,
            "conclusion": conclusion,
            "data_source": PROVIDER_NAME,
            "platform_deployment_id": str(hist_id),
            "url": f"{self.server}/applications/{app}" if self.server else "",
            "deployed_by": "argocd",
            "release_id": "",
            "artifacts": "",
            "created_at": started or finished,
            "started_at": started,
            "completed_at": finished,
            "rollback_started_at": "",
            "rollback_completed_at": "",
            "duration_seconds": duration,
        }

    @staticmethod
    def _derive_status(sync_status: str, health_status: str):
        """sync+health → (status, conclusion) per deployment schema enums."""
        if sync_status == "Synced" and health_status == "Healthy":
            return "success", "success"
        if sync_status == "OutOfSync":
            return "in_progress", ""
        if health_status in ("Degraded",):
            return "failure", "failure"
        if health_status in ("Progressing",):
            return "in_progress", ""
        if health_status in ("Missing", "Unknown"):
            return "failure", "failure"
        return "in_progress", ""

    @staticmethod
    def _duration_seconds(started: str, finished: str) -> int:
        """ISO8601 pair → seconds; 0 when either missing."""
        if not started or not finished:
            return 0
        from datetime import datetime, timezone

        def _parse(s: str) -> Optional[datetime]:
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
            except (ValueError, TypeError):
                return None
        a, b = _parse(started), _parse(finished)
        if not a or not b:
            return 0
        return max(0, int((b - a).total_seconds()))

    # ---- HTTP ------------------------------------------------------------

    def _ssl_ctx(self):
        if not self.insecure:
            return None
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _login(self) -> str:
        """POST /api/v1/session with username/password → session token."""
        req = urllib.request.Request(
            f"{self.server}/api/v1/session",
            data=json.dumps({"username": self.username,
                             "password": self.password}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30, context=self._ssl_ctx()) as resp:
            return json.loads(resp.read().decode("utf-8"))["token"]

    def _get(self, path: str, _retried: bool = False) -> Dict[str, Any]:
        if not self.token and self.username and self.password:
            self.token = self._login()
        url = f"{self.server}{path}"
        req = urllib.request.Request(url)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30, context=self._ssl_ctx()) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # Session tokens expire (default 24h); with login credentials
            # configured, mint a fresh token once and retry the request.
            if e.code == 401 and self.username and self.password and not _retried:
                logger.info("argocd: 401 — re-login and retry %s", path)
                self.token = self._login()
                return self._get(path, _retried=True)
            raise RuntimeError(f"argocd GET {path} → HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")
