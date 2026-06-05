#!/usr/bin/env python3
"""
CMS workspace devops entity verification script.

Queries a CMS workspace for all devops.* domain entities and verifies
that the full devops enrichment chain (GitLab or Codeup -> ACR -> ACK -> SLS -> CMS)
has successfully landed entity data in the workspace's EntityStore.

Usage:
  python3 query_cms_devops.py --config ../config
"""
import time

from cms_script_common import build_argument_parser, create_cms_client, load_cms_runtime


def query_cms(client, workspace, query_str, label):
    from alibabacloud_cms20240330 import models as CmsModels
    from alibabacloud_tea_util import models as UtilModels

    current_time = int(time.time())
    five_minutes_ago = current_time - 600

    print(f"\n{'=' * 80}")
    print(f"QUERY: {label}")
    print(f"SPL: {query_str}")
    print(f"{'=' * 80}")

    headers = CmsModels.GetEntityStoreDataHeaders()
    request = CmsModels.GetEntityStoreDataRequest(
        from_=five_minutes_ago, to=current_time, query=query_str
    )
    runtime = UtilModels.RuntimeOptions()
    response = client.get_entity_store_data_with_options(workspace, request, headers, runtime)

    print(f"HTTP {response.status_code}")

    if response.status_code == 200 and response.body:
        data = response.body.to_map()
        headers_list = data.get("header", [])
        rows = data.get("data", [])
        print(f"Headers: {headers_list}")
        print(f"Row count: {len(rows)}")

        for i, row in enumerate(rows[:5]):
            print(f"  [{i}] {row}")

        return {"status": response.status_code, "headers": headers_list, "row_count": len(rows), "rows": rows}
    else:
        print(f"Non-200 or empty body")
        return {"status": response.status_code, "headers": [], "row_count": 0, "rows": []}


def main():
    parser = build_argument_parser("Query devops.* entities from a CMS workspace")
    args = parser.parse_args()
    runtime_cfg = load_cms_runtime(args.config)
    client = create_cms_client(runtime_cfg)
    workspace = runtime_cfg.workspace

    queries = [
        (".entity with(domain='devops') |project __entity_id__, __entity_type__, __domain__", "All devops domain entities"),
        (".entity with(domain='devops', type='devops.code_repository') |project __entity_id__, __entity_type__, __domain__", "devops.code_repository"),
        (".entity with(domain='devops', type='devops.code_release') |project __entity_id__, __entity_type__, __domain__", "devops.code_release"),
        (".entity with(domain='devops', type='devops.image') |project __entity_id__, __entity_type__, __domain__", "devops.image"),
        (".entity with(domain='devops', type='devops.image_registry') |project __entity_id__, __entity_type__, __domain__", "devops.image_registry"),
        (".entity with(domain='devops', type='devops.developer') |project __entity_id__, __entity_type__, __domain__", "devops.developer"),
        (".entity |project __entity_id__, __entity_type__, __domain__", "ALL entity types (no domain filter)"),
        (".entity |project __entity_type__ |sort __entity_type__", "All unique entity types"),
    ]

    results = {}
    for query_str, label in queries:
        result = query_cms(client, workspace, query_str, label)
        results[label] = result
        time.sleep(0.3)

    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    for label, result in results.items():
        print(f"  [{result['status']}] {label}: {result['row_count']} rows")

    devops_labels = [
        "devops.code_repository", "devops.code_release", "devops.image",
        "devops.image_registry", "devops.developer",
    ]
    has_devops = any(results.get(l, {}).get("row_count", 0) > 0 for l in devops_labels)

    print(f"\n{'=' * 80}")
    print("VERDICT")
    print(f"{'=' * 80}")
    if has_devops:
        print("devops.* data EXISTS in CMS workspace")
    else:
        print("devops.* data NOT FOUND in CMS workspace")

    all_types = results.get("All unique entity types", {})
    if all_types.get("row_count", 0) > 0:
        types = set()
        for row in all_types.get("rows", [])[:200]:
            if row:
                types.add(row[0])
        print(f"\nEntity types in workspace ({len(types)}):")
        for t in sorted(types):
            print(f"  {t}")


if __name__ == "__main__":
    main()
