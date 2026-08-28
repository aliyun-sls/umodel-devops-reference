"""CI adapter abstract base (standalone CI systems: Jenkins / Yunxiao Flow / ...).

Mirrors `deploy_base.py` (IDeployAdapter) in style: the docstring is the
contract; subclasses translate provider APIs into it.

Why a separate axis: GitLab CI lives inside the git provider, so it stays on
IGitAdapter as optional methods. Standalone CI systems (Jenkins, Yunxiao
Flow, Tekton, GitHub Actions) are NOT git providers — they implement this
interface instead. ("第一个寄生、第二个来临才抽基类"：GitLab CI 是第一个
实例所以寄生在 IGitAdapter；Jenkins 的到来触发了这个基类。)

Unified output schemas
----------------------
``list_pipelines()`` items (pipeline *definitions*, e.g. Jenkins jobs):
    {pipeline_id, repository_id, name, file_path, description,
     data_source, platform_pipeline_id, url, is_active,
     created_at, updated_at}
    ``pipeline_id`` = ``<data_source>:<platform_pipeline_id>``.
    ``repository_id`` may be "" when the CI system does not bind the
    definition to a repo (Jenkins freestyle jobs); when a config-provided
    repo mapping exists, fill it to enable repository_contains_pipeline edges.

``list_pipeline_runs()`` items (pipeline *executions*, e.g. Jenkins builds):
    {run_id, pipeline_id, repository_id, number, pr_id, commit_sha,
     branch, trigger_type, status, conclusion, data_source,
     platform_run_id, url, triggered_by, stages, created_at, started_at,
     completed_at, duration_seconds, queue_duration_seconds}
    ``status`` ∈ queued/in_progress/success/failure/cancelled/skipped;
    ``conclusion`` ∈ success/failure/cancelled/timeout (or "").
    Providers must not raise on partial data: fill "" / 0 and keep going.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ICIAdapter(ABC):
    """Unified interface for standalone CI systems (Jenkins / Yunxiao Flow / ...)."""

    @abstractmethod
    def list_pipelines(self) -> List[Dict[str, Any]]:
        """Return pipeline definitions in the unified schema above."""

    @abstractmethod
    def list_pipeline_runs(self) -> List[Dict[str, Any]]:
        """Return pipeline executions in the unified schema above."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Literal written into ``data_source`` (e.g. ``"jenkins"``)."""

    @abstractmethod
    def validate_config(self) -> bool:
        """Confirm credentials / endpoint / connectivity."""
