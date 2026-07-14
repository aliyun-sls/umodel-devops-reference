#!/usr/bin/env python3
"""
Shared helpers for CMS verification scripts.

All runtime settings are loaded from the repository config directory so the
verification tooling follows the same configuration source as the main
generator entrypoint.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config_loader import ConfigLoader


DEFAULT_CONFIG_DIR = str(PROJECT_ROOT / "config")


@dataclass
class CmsRuntimeConfig:
    config_dir: str
    endpoint: str
    workspace: str
    access_key_id: str
    access_key_secret: str
    sls_endpoint: str
    sls_project: str
    sls_access_key_id: str
    sls_access_key_secret: str
    sls_relationship_logstore: str
    namespace_filter: str
    cluster_id: str
    data_source: str


def build_argument_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_DIR,
        help=f"Config directory path (default: {DEFAULT_CONFIG_DIR})",
    )
    return parser


def load_cms_runtime(config_dir: str) -> CmsRuntimeConfig:
    loader = ConfigLoader(config_dir)
    cms_config = loader.get_cms_config()
    kubernetes_config = loader.get_kubernetes_config()
    sls_config = loader.get_sls_config()

    endpoint = cms_config.get("endpoint", "")
    workspace = cms_config.get("workspace", "")
    access_key_id = cms_config.get("access_key_id", "")
    access_key_secret = cms_config.get("access_key_secret", "")
    sls_endpoint = sls_config.get("endpoint", "")
    sls_project = sls_config.get("project", "")
    sls_access_key_id = sls_config.get("access_key_id") or access_key_id
    sls_access_key_secret = sls_config.get("access_key_secret") or access_key_secret
    relationship_logstores = sls_config.get("logstore_mapping", {}).get("relationships", {})
    sls_relationship_logstore = (
        relationship_logstores.get("pod_uses_docker_image")
        or relationship_logstores.get("pod_uses_image")
        or f"{workspace}__topo"
    )
    namespace_filter = cms_config.get("namespace_filter") or kubernetes_config.get(
        "namespace_filter", ""
    )
    cluster_id = kubernetes_config.get("cluster_id", "")
    data_source = kubernetes_config.get("data_source", "")

    missing = [
        name
        for name, value in (
            ("cms.endpoint", endpoint),
            ("cms.workspace", workspace),
            ("cms.access_key_id", access_key_id),
            ("cms.access_key_secret", access_key_secret),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing required CMS config values in app_config.yaml: "
            + ", ".join(missing)
        )

    return CmsRuntimeConfig(
        config_dir=config_dir,
        endpoint=endpoint,
        workspace=workspace,
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        sls_endpoint=sls_endpoint,
        sls_project=sls_project,
        sls_access_key_id=sls_access_key_id,
        sls_access_key_secret=sls_access_key_secret,
        sls_relationship_logstore=sls_relationship_logstore,
        namespace_filter=namespace_filter,
        cluster_id=cluster_id,
        data_source=data_source,
    )


def create_cms_client(runtime_cfg: CmsRuntimeConfig):
    from alibabacloud_cms20240330.client import Client as CmsClient
    from alibabacloud_credentials.client import Config as CredConfig
    from alibabacloud_credentials.client import Client as CredClient
    from alibabacloud_tea_openapi import models as OpenApiModels

    cred_cfg = CredConfig(
        type="access_key",
        access_key_id=runtime_cfg.access_key_id,
        access_key_secret=runtime_cfg.access_key_secret,
    )
    credential = CredClient(cred_cfg)
    config = OpenApiModels.Config(endpoint=runtime_cfg.endpoint, credential=credential)
    return CmsClient(config)
