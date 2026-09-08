"""Shared GitHub REST client (stdlib urllib, no extra dependency).

Used by both GitHubAdapter (git provider axis) and GitHubActionsAdapter
(CI axis). Auth: ``Authorization: Bearer <token>`` when a token is set;
anonymous access works too but is capped at 60 requests/hour/IP by GitHub.

Also owns repo-scope resolution: both axes read the same ``github:`` config
section, which may name explicit repos, an organization, and/or a user.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://api.github.com"
API_VERSION = "2022-11-28"
PER_PAGE = 100


class GitHubClient:
    """Minimal GitHub REST client with page-loop pagination."""

    def __init__(self, api_url: str = "", token: str = ""):
        self.api_url = (api_url or DEFAULT_API_URL).rstrip("/")
        self.token = token or ""

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Single GET; returns decoded JSON (dict or list)."""
        url = f"{self.api_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", API_VERSION)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            # GitHub rate-limit (primary + secondary) surfaces as 403/429.
            if e.code in (403, 429) and "rate limit" in body.lower():
                raise RuntimeError(
                    f"github GET {path} rate-limited (HTTP {e.code}); "
                    f"set github.token or reduce fetch volume: {body}")
            raise RuntimeError(f"github GET {path} → HTTP {e.code}: {body}")

    def get_paginated(self, path: str, params: Optional[Dict[str, Any]] = None,
                      wrapper: str = "", max_pages: int = 0) -> List[Any]:
        """Page-loop until a short page. max_pages=0 means no cap.

        ``wrapper`` names the list key for endpoints that wrap their page in
        an object (e.g. "workflows", "workflow_runs"); plain list endpoints
        leave it empty.
        """
        out: List[Any] = []
        page = 1
        while True:
            p = dict(params or {})
            p.update({"per_page": PER_PAGE, "page": page})
            data = self.get(path, p)
            items = data if isinstance(data, list) else (data.get(wrapper) or [])
            out.extend(items)
            if len(items) < PER_PAGE:
                return out
            page += 1
            if max_pages and page > max_pages:
                return out


def resolve_repos(client: GitHubClient, config: Dict[str, Any],
                  ) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Resolve the repo scope of a ``github:`` config section.

    Returns a deduped list of (full_name, repo_id, repo_object) tuples from:
      - repos: ["owner/name", ...]   explicit allowlist (fetched per repo)
      - organization: "<org>"        all org repos (paginated)
      - user: "<user>"               all repos of a user (paginated)
    Repos that 404 or are unreadable are skipped with a warning — partial
    scope must never abort a cycle.
    """
    repos: Dict[str, Tuple[str, str, Dict[str, Any]]] = {}

    def _add(obj: Dict[str, Any]):
        full_name = obj.get("full_name", "")
        repo_id = obj.get("id", "")
        if full_name and repo_id:
            repos[str(repo_id)] = (full_name, str(repo_id), obj)

    for full_name in (config.get("repos") or []):
        full_name = str(full_name).strip().strip("/")
        if not full_name:
            continue
        try:
            _add(client.get(f"/repos/{full_name}"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("github: repo %s not readable, skipped: %s", full_name, exc)

    organization = (config.get("organization") or "").strip()
    if organization:
        try:
            for obj in client.get_paginated(f"/orgs/{organization}/repos",
                                            {"type": "all"}):
                _add(obj)
        except Exception as exc:  # noqa: BLE001
            logger.warning("github: org %s not listable, skipped: %s", organization, exc)

    user = (config.get("user") or "").strip()
    if user:
        try:
            for obj in client.get_paginated(f"/users/{user}/repos"):
                _add(obj)
        except Exception as exc:  # noqa: BLE001
            logger.warning("github: user %s not listable, skipped: %s", user, exc)

    return list(repos.values())
