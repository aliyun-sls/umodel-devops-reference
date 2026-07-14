#!/usr/bin/env python3
"""
CMS workspace devops entity and topology field-level verification script.

Performs targeted queries to verify that specific known entities
(repository, release, docker_image, artifact, user) contain
expected field values in the CMS workspace EntityStore. It also prints recent
pod -> docker_image topology records from the configured SLS relationship
logstore so image-match evidence has a concrete source.

Usage:
  python3 verify_devops_details.py --config ../config
"""
import time

from cms_script_common import build_argument_parser, create_cms_client, load_cms_runtime


def query(client, workspace, query_str, label):
    from alibabacloud_cms20240330 import models as CmsModels
    from alibabacloud_tea_util import models as UtilModels

    current_time = int(time.time())

    print(f"\n{'=' * 80}")
    print(f"QUERY: {label}")
    print(f"SPL: {query_str}")
    print(f"{'=' * 80}")

    headers = CmsModels.GetEntityStoreDataHeaders()
    request = CmsModels.GetEntityStoreDataRequest(
        from_=current_time - 600, to=current_time, query=query_str
    )
    runtime = UtilModels.RuntimeOptions()
    response = client.get_entity_store_data_with_options(workspace, request, headers, runtime)

    print(f"HTTP {response.status_code}, rows: {len(response.body.to_map().get('data', []))}")

    if response.status_code == 200 and response.body:
        data = response.body.to_map()
        headers_list = data.get("header", [])
        rows = data.get("data", [])

        for i, row in enumerate(rows):
            parts = []
            for j, col in enumerate(headers_list):
                val = row[j] if j < len(row) else "N/A"
                if len(str(val)) > 80:
                    val = str(val)[:80] + "..."
                parts.append(f"{col}={val}")
            print(f"  [{i}] " + "  ".join(parts))


def query_pod_image_edges(runtime_cfg):
    """Print recent pod -> docker_image relationship evidence from SLS."""
    missing = [
        name
        for name, value in (
            ("sls.endpoint", runtime_cfg.sls_endpoint),
            ("sls.project", runtime_cfg.sls_project),
            ("sls.access_key_id", runtime_cfg.sls_access_key_id),
            ("sls.access_key_secret", runtime_cfg.sls_access_key_secret),
            ("sls relationship logstore", runtime_cfg.sls_relationship_logstore),
        )
        if not value
    ]
    if missing:
        print(
            "\nTOPOLOGY EVIDENCE SKIPPED: missing SLS config values: "
            + ", ".join(missing)
        )
        return

    try:
        from aliyun.log import GetLogsRequest, LogClient
    except ImportError as exc:
        print(f"\nTOPOLOGY EVIDENCE SKIPPED: aliyun-log-python-sdk unavailable ({exc})")
        return

    now = int(time.time())
    query_str = (
        '__src_entity_type__:"k8s.pod" AND '
        '__dest_entity_type__:"devops.docker_image"'
    )
    print(f"\n{'=' * 80}")
    print("QUERY: pod -> docker_image topology evidence")
    print(f"Logstore: {runtime_cfg.sls_project}/{runtime_cfg.sls_relationship_logstore}")
    print(f"SLS query: {query_str}")
    print(f"{'=' * 80}")

    client = LogClient(
        runtime_cfg.sls_endpoint,
        runtime_cfg.sls_access_key_id,
        runtime_cfg.sls_access_key_secret,
    )
    request = GetLogsRequest(
        project=runtime_cfg.sls_project,
        logstore=runtime_cfg.sls_relationship_logstore,
        fromTime=now - 600,
        toTime=now,
        query=query_str,
        line=20,
        offset=0,
        reverse=True,
    )
    try:
        logs = client.get_logs(request).get_logs()
    except Exception as exc:  # noqa: BLE001
        print(f"TOPOLOGY EVIDENCE FAILED: {exc}")
        return

    print(f"Row count: {len(logs)}")
    fields = (
        "container_image",
        "repository",
        "tag",
        "docker_image_id",
        "__src_entity_id__",
        "__dest_entity_id__",
        "__relation_type__",
        "__link_type__",
        "__last_observed_time__",
        "__keep_alive_seconds__",
    )
    for index, log in enumerate(logs):
        contents = log.get_contents()
        values = "  ".join(
            f"{field}={contents.get(field, 'N/A')}" for field in fields
        )
        print(f"  [{index}] {values}")


def main():
    parser = build_argument_parser("Verify devops.* entity fields from a CMS workspace")
    args = parser.parse_args()
    runtime_cfg = load_cms_runtime(args.config)
    client = create_cms_client(runtime_cfg)
    workspace = runtime_cfg.workspace

    queries = [
        (
            ".entity with(domain='devops', type='devops.repository') "
            "|project __entity_id__, repository_id, name, url, data_source",
            "repository - full fields",
        ),
        (
            ".entity with(domain='devops', type='devops.release') "
            "|project __entity_id__, release_id, tag_name, repository_id, name",
            "release - full fields",
        ),
        (
            ".entity with(domain='devops', type='devops.docker_image') "
            "|project __entity_id__, docker_image_id, artifact_id, repository, tag, full_image_name, registry",
            "docker_image - full fields",
        ),
        (
            ".entity with(domain='devops', type='devops.artifact') "
            "|project __entity_id__, artifact_id, platform_artifact_id, name, tag_name, storage_location",
            "artifact - full fields",
        ),
        (
            ".entity with(domain='devops', type='devops.user') "
            "|project __entity_id__, user_id, full_name, email, data_source",
            "user - full fields",
        ),
        (
            ".entity with(domain='devops') |project __entity_type__ |sort __entity_type__",
            "All devops entity types summary",
        ),
    ]

    for query_str, label in queries:
        query(client, workspace, query_str, label)
        time.sleep(0.3)

    query_pod_image_edges(runtime_cfg)


if __name__ == "__main__":
    main()
