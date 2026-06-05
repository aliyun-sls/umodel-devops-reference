import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

from adapters import create_git_adapter
from config.config_loader import ConfigLoader
from generator.sls_data_generator import SlsDataGenerator
from sender.sls_data_sender import SlsDataSender
from shared.data_context import SharedDataContext
from tasks.code_release_sourced_from_code_repository_task import CodeReleaseSourcedFromCodeRepositoryTask
from tasks.code_release_task import CodeReleaseTask
from tasks.code_repository_task import CodeRepositoryTask
from tasks.developer_manages_code_repository_task import DeveloperManagesCodeRepositoryTask
from tasks.developer_task import DeveloperTask
from tasks.image_registry_contains_image_task import ImageRegistryContainsImageTask
from tasks.image_registry_task import ImageRegistryTask
from tasks.image_sourced_from_code_release_task import ImageSourcedFromCodeReleaseTask
from tasks.image_task import ImageTask
from tasks.kubernetes_pod_task import KubernetesPodTask
from tasks.pod_uses_image_task import PodUsesImageTask
from tasks.static_topo_task import StaticTopoTask

logger = logging.getLogger(__name__)


# Critical tasks gate `partial_success` vs `error` for the cycle.
# Naming kept provider-agnostic so codeup runs follow the same logic.
CRITICAL_GIT_TASKS = {"code_repository", "developer", "code_release"}

# Placeholder tokens that indicate a sample config block has not been
# populated yet. Covers both gitlab and codeup samples.
PLACEHOLDER_TOKENS = {
    # GitLab
    "<YOUR_GITLAB_PAT>",
    # Codeup
    "<YOUR_ORGANIZATION_ID>",
    "<YOUR_ALIYUN_AK>",
    "<YOUR_ALIYUN_SK>",
    # Shared
    "<YOUR_ACR_INSTANCE_ID>",
    "<YOUR_ACCESS_KEY_ID>",
    "<YOUR_ACCESS_KEY_SECRET>",
    "<YOUR_CMS_ENDPOINT>",
    "<YOUR_CMS_WORKSPACE>",
    "<YOUR_NAMESPACE_FILTER>",
    "<YOUR_CLUSTER_ID>",
    "<YOUR_SLS_PROJECT>",
    "<YOUR_ENTITY_NAME>",
    "<YOUR_TOPO_NAME>",
    "<YOUR_REGION_ID>",
}


def _has_real_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text or text in PLACEHOLDER_TOKENS:
        return False
    return not (text.startswith("<") and text.endswith(">"))


class DevOpsDataOrchestrator:
    # Public alias kept for backwards-compat with any external callers.
    CRITICAL_GITLAB_TASKS = CRITICAL_GIT_TASKS

    def __init__(self, config_dir: str = None, enable_shared_data: bool = True):
        self.config_loader = ConfigLoader(config_dir)
        if not self.config_loader.validate_config():
            raise ValueError("Configuration validation failed")

        self.git_provider_type = self.config_loader.get_git_provider_type()
        self.git_adapter = create_git_adapter(
            self.git_provider_type,
            self.config_loader.get_git_provider_config(),
        )

        self.enable_shared_data = enable_shared_data
        self.shared_context = None
        if enable_shared_data:
            tasks_config = self.config_loader.get_tasks_config()
            self.shared_context = SharedDataContext(tasks_config.get("shared_data_ttl", 300))

        self._initialize_components()
        self._setup_task_dependencies()
        self._attach_task_runtime_context()

    def _initialize_components(self):
        provider_config = self.config_loader.get_git_provider_config()
        sls_config = self.config_loader.get_sls_config()
        acr_config = self.config_loader.app_config.get("acr", {})
        cms_config = self.config_loader.app_config.get("cms", {})
        kubernetes_config = self.config_loader.app_config.get("kubernetes", {})
        static_topo_config = dict(self.config_loader.app_config.get("static_topo", {}))
        mapping_config_path = os.path.join(self.config_loader.config_dir, "data_mapping.yaml")
        static_topo_path = static_topo_config.get("static_topo_config", "config/static_topo.yaml")
        if static_topo_path and not os.path.isabs(static_topo_path):
            static_topo_config["static_topo_config"] = os.path.join(
                self.config_loader.config_dir, os.path.basename(static_topo_path)
            )

        self.data_generator = SlsDataGenerator(mapping_config_path)
        self.data_sender = SlsDataSender(sls_config)
        self.skip_sls_upload = set(self.config_loader.get_tasks_config().get("skip_sls_upload", []))

        self.tasks = {
            # Git-provider-aware tasks: inject adapter + carry provider_config
            # for niche options (release_tag, fetch_details).
            "code_repository": CodeRepositoryTask(provider_config, self.git_adapter),
            "developer": DeveloperTask(provider_config, self.git_adapter),
            "code_release": CodeReleaseTask(provider_config, self.git_adapter),
            # Provider-agnostic relationship tasks
            "developer_manages_code_repository": DeveloperManagesCodeRepositoryTask(provider_config),
            "code_release_sourced_from_code_repository": CodeReleaseSourcedFromCodeRepositoryTask(provider_config),
            # ACR / K8s tasks (provider-agnostic)
            "image_registry": ImageRegistryTask(acr_config),
            "image": ImageTask(acr_config),
            "image_registry_contains_image": ImageRegistryContainsImageTask(acr_config),
            "image_sourced_from_code_release": ImageSourcedFromCodeReleaseTask(acr_config),
            "kubernetes_pod": KubernetesPodTask(self._merge_k8s_configs(cms_config, kubernetes_config)),
            "pod_uses_image": PodUsesImageTask(cms_config),
            "static_topo": StaticTopoTask(static_topo_config),
        }

        if self.shared_context:
            for task_name, task in self.tasks.items():
                task.set_shared_context(self.shared_context)
                task.task_name = task_name

    def _merge_k8s_configs(self, cms_config: Dict[str, Any], kubernetes_config: Dict[str, Any]) -> Dict[str, Any]:
        merged = {}
        data_source = kubernetes_config.get("data_source", "k8s").lower()
        merged["data_source"] = data_source
        merged["namespace_filter"] = kubernetes_config.get("namespace_filter") or cms_config.get("namespace_filter", "")
        merged["cluster_id"] = kubernetes_config.get("cluster_id") or cms_config.get("cluster_id", "default-cluster")
        merged["endpoint"] = cms_config.get("endpoint")
        merged["workspace"] = cms_config.get("workspace")
        merged["access_key_id"] = cms_config.get("access_key_id")
        merged["access_key_secret"] = cms_config.get("access_key_secret")
        merged["kubeconfig_path"] = kubernetes_config.get("kubeconfig_path")
        merged["k8s_context"] = kubernetes_config.get("k8s_context")
        return merged

    def _setup_task_dependencies(self):
        if not self.shared_context:
            return
        for task_name, task in self.tasks.items():
            deps = task.get_dependencies()
            if deps:
                self.shared_context.set_task_dependency(task_name, deps)
        for task_name, deps in self.config_loader.get_tasks_config().get("dependencies", {}).items():
            if task_name in self.tasks:
                self.shared_context.set_task_dependency(task_name, deps)

    def _attach_task_runtime_context(self):
        for task in self.tasks.values():
            task.config_dir = self.config_loader.config_dir

    def run_single_cycle(self) -> bool:
        result = self.run_single_cycle_result()
        return result["execution_summary"]["status"] in {"success", "partial_success"}

    def run_single_cycle_result(self) -> Dict[str, Any]:
        start_time = time.time()
        executed_tasks = []
        skipped_tasks = []
        failed_tasks = []
        entities_generated = []
        relationships_generated = []
        warnings = []
        try:
            if self.shared_context:
                self.shared_context.clear_expired()
            enabled_tasks = self.config_loader.get_tasks_config().get("enabled", [])
            execution_order = (
                self.shared_context.get_execution_order(enabled_tasks) if self.shared_context else enabled_tasks
            )

            for task_name in execution_order:
                task = self.tasks.get(task_name)
                if not task:
                    continue
                if not task.validate_config():
                    warning = f"Skipping task '{task_name}' because configuration is invalid or incomplete"
                    skipped_tasks.append({"task": task_name, "reason": "invalid_or_incomplete_config"})
                    warnings.append(warning)
                    logger.warning(warning)
                    continue

                try:
                    raw_data = task.fetch_data()
                    if raw_data is None:
                        executed_tasks.append({"task": task_name, "count": 0, "task_type": task.get_task_type()})
                        continue
                    if self.shared_context:
                        self.shared_context.set_data(f"{task_name}_raw_data", raw_data, "raw_data", task_name)
                    if task.get_task_type() == "entity":
                        entity_data = self.data_generator.generate_entity_data(task_name, raw_data)
                        entity_count = len(entity_data or [])
                        executed_tasks.append({"task": task_name, "count": entity_count, "task_type": "entity"})
                        entities_generated.append({"type": task_name, "count": entity_count})
                        if entity_data and self.shared_context:
                            self.shared_context.set_data(f"{task_name}_entity_data", entity_data, "entity_data", task_name)
                        if task_name not in self.skip_sls_upload and entity_data:
                            self.data_sender.send_entity_data(task_name, entity_data)
                    else:
                        relation_count = len(raw_data or [])
                        executed_tasks.append({"task": task_name, "count": relation_count, "task_type": "relationship"})
                        relationships_generated.append({"type": task_name, "count": relation_count})
                        if task_name not in self.skip_sls_upload and raw_data:
                            self.data_sender.send_relationship_data(task_name, raw_data)
                except Exception as exc:
                    error_text = str(exc)
                    failed_tasks.append({"task": task_name, "error": error_text})
                    warnings.append(f"Task '{task_name}' failed: {error_text}")
                    logger.error("Task '%s' failed during single cycle: %s", task_name, exc)
                    continue

            result = self._build_cycle_result(
                start_time=start_time,
                executed_tasks=executed_tasks,
                skipped_tasks=skipped_tasks,
                failed_tasks=failed_tasks,
                entities_generated=entities_generated,
                relationships_generated=relationships_generated,
                warnings=warnings,
            )

            logger.info(
                "Single cycle (provider=%s) completed in %.2fs (status=%s, executed=%s, skipped=%s, failed=%s)",
                self.git_provider_type,
                result["execution_summary"]["duration_seconds"],
                result["execution_summary"]["status"],
                executed_tasks,
                skipped_tasks,
                failed_tasks,
            )
            return result
        except Exception as exc:
            logger.error("Error in single cycle execution: %s", exc)
            return self._build_cycle_result(
                start_time=start_time,
                executed_tasks=executed_tasks,
                skipped_tasks=skipped_tasks,
                failed_tasks=failed_tasks + [{"task": "__orchestrator__", "error": str(exc)}],
                entities_generated=entities_generated,
                relationships_generated=relationships_generated,
                warnings=warnings + [f"Single cycle aborted: {str(exc)}"],
            )

    def _build_cycle_result(
        self,
        start_time: float,
        executed_tasks: Any,
        skipped_tasks: Any,
        failed_tasks: Any,
        entities_generated: Any,
        relationships_generated: Any,
        warnings: Any,
    ) -> Dict[str, Any]:
        executed_task_names = {item["task"] for item in executed_tasks}
        skipped_task_names = {item["task"] for item in skipped_tasks}
        failed_task_names = {item["task"] for item in failed_tasks}

        critical_executed = CRITICAL_GIT_TASKS & executed_task_names
        critical_skipped = CRITICAL_GIT_TASKS & skipped_task_names
        critical_failed = CRITICAL_GIT_TASKS & failed_task_names

        if critical_failed or critical_skipped or not critical_executed:
            status = "error"
        elif failed_tasks or skipped_tasks:
            status = "partial_success"
        else:
            status = "success"

        return {
            "execution_summary": {
                "status": status,
                "git_provider": self.git_provider_type,
                "duration_seconds": round(time.time() - start_time, 3),
                "executed_task_count": len(executed_tasks),
                "skipped_task_count": len(skipped_tasks),
                "failed_task_count": len(failed_tasks),
                "critical_tasks": sorted(CRITICAL_GIT_TASKS),
            },
            "executed_tasks": executed_tasks,
            "skipped_tasks": skipped_tasks,
            "failed_tasks": failed_tasks,
            "entities_generated": entities_generated,
            "relationships_generated": relationships_generated,
            "warnings": warnings,
        }

    def run_continuous(self, interval: Optional[int] = None) -> None:
        if interval is None:
            interval = self.config_loader.get_tasks_config().get("interval", 300)
        while True:
            try:
                self.run_single_cycle()
                time.sleep(interval)
            except KeyboardInterrupt:
                break

    def get_status(self) -> Dict[str, Any]:
        status = {
            "timestamp": datetime.now().isoformat(),
            "git_provider": self.git_provider_type,
            "components": {
                "config_loader": "initialized",
                "data_generator": "initialized",
                "data_sender": "initialized",
                "shared_context": "enabled" if self.shared_context else "disabled",
            },
            "tasks": {},
            "supported_entities": self.data_generator.get_supported_entities(),
            "supported_relationships": self.data_generator.get_supported_relationships(),
        }
        if self.shared_context:
            status["shared_data"] = self.shared_context.get_status()
        for task_name, task in self.tasks.items():
            try:
                config_valid = task.validate_config()
                status["tasks"][task_name] = {
                    "config_valid": config_valid,
                    "runtime_ready": self._is_task_runtime_ready(task_name),
                    "class": task.__class__.__name__,
                }
            except Exception as exc:
                status["tasks"][task_name] = {
                    "config_valid": False,
                    "runtime_ready": False,
                    "error": str(exc),
                }
        return status

    def _is_task_runtime_ready(self, task_name: str) -> bool:
        provider_config = self.config_loader.get_git_provider_config()
        acr_config = self.config_loader.get_acr_config()
        cms_config = self.config_loader.get_cms_config()
        kubernetes_config = self.config_loader.get_kubernetes_config()
        sls_config = self.config_loader.get_sls_config()

        if task_name in CRITICAL_GIT_TASKS:
            if self.git_provider_type == "gitlab":
                return _has_real_value(provider_config.get("url")) and _has_real_value(
                    provider_config.get("access_token")
                )
            if self.git_provider_type == "codeup":
                return (
                    _has_real_value(provider_config.get("organization_id"))
                    and _has_real_value(provider_config.get("access_key_id"))
                    and _has_real_value(provider_config.get("access_key_secret"))
                )
            return False
        if task_name in {"image_registry", "image"}:
            return (
                _has_real_value(acr_config.get("instance_id"))
                and _has_real_value(acr_config.get("access_key_id"))
                and _has_real_value(acr_config.get("access_key_secret"))
            )
        if task_name == "kubernetes_pod":
            data_source = str(kubernetes_config.get("data_source", "k8s")).lower()
            if data_source == "cms":
                return (
                    _has_real_value(cms_config.get("endpoint"))
                    and _has_real_value(cms_config.get("workspace"))
                    and _has_real_value(cms_config.get("access_key_id"))
                    and _has_real_value(cms_config.get("access_key_secret"))
                )
            return _has_real_value(kubernetes_config.get("kubeconfig_path"))
        if task_name in {
            "code_release_sourced_from_code_repository",
            "developer_manages_code_repository",
            "image_registry_contains_image",
            "image_sourced_from_code_release",
            "pod_uses_image",
            "static_topo",
        }:
            return True
        if task_name == "sls_sender":
            return _has_real_value(sls_config.get("endpoint")) and _has_real_value(sls_config.get("project"))
        return True
