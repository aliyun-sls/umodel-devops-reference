#!/usr/bin/env python3
"""
CMS workspace devops entity field-level detail verification script.

Performs targeted queries to verify that specific known entities
(code_repository, code_release, image, image_registry) contain
expected field values in the CMS workspace EntityStore.

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


def main():
    parser = build_argument_parser("Verify devops.* entity fields from a CMS workspace")
    args = parser.parse_args()
    runtime_cfg = load_cms_runtime(args.config)
    client = create_cms_client(runtime_cfg)
    workspace = runtime_cfg.workspace

    queries = [
        (
            ".entity with(domain='devops', type='devops.code_repository') "
            "|project __entity_id__, repo_id, repo_name, repo_url, git_provider",
            "code_repository - full fields",
        ),
        (
            ".entity with(domain='devops', type='devops.code_release') "
            "|project __entity_id__, release_id, tag, repo_id, repo_name",
            "code_release - full fields",
        ),
        (
            ".entity with(domain='devops', type='devops.image') "
            "|project __entity_id__, image_id, image_name, image_tag, full_image_name, registry_id",
            "image - full fields",
        ),
        (
            ".entity with(domain='devops', type='devops.image_registry') "
            "|project __entity_id__, registry_id, registry_name, registry_url",
            "image_registry - full fields",
        ),
        (
            ".entity with(domain='devops') |project __entity_type__ |sort __entity_type__",
            "All devops entity types summary",
        ),
    ]

    for query_str, label in queries:
        query(client, workspace, query_str, label)
        time.sleep(0.3)


if __name__ == "__main__":
    main()
