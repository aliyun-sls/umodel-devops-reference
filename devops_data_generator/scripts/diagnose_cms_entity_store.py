#!/usr/bin/env python3
"""
CMS workspace entity store diagnostic script.

Checks the full CMS workspace configuration and data surface:
  1. Workspace metadata (region, backing SLS project)
  2. All entity types present in the EntityStore
  3. Devops domain entity presence

Useful for diagnosing why custom entities are not appearing in CMS
workspace queries, and for verifying the SLS project mapping is correct.

Usage:
  python3 diagnose_cms_entity_store.py --config ../config
"""
import time

from cms_script_common import build_argument_parser, create_cms_client, load_cms_runtime


def main():
    parser = build_argument_parser("Diagnose CMS workspace entity store content")
    args = parser.parse_args()
    runtime_cfg = load_cms_runtime(args.config)
    client = create_cms_client(runtime_cfg)
    workspace = runtime_cfg.workspace

    # 1. Workspace info
    print("=" * 80)
    print("1. WORKSPACE INFO")
    print("=" * 80)
    try:
        from alibabacloud_tea_util import models as UtilModels

        resp = client.get_workspace_with_options(workspace, {}, UtilModels.RuntimeOptions())
        print(f"HTTP {resp.status_code}")
        if resp.body:
            body = resp.body.to_map()
            # Only print non-sensitive fields
            safe_fields = ["createTime", "description", "displayName", "lastModifyTime",
                           "regionId", "slsProject", "workspaceName"]
            for k in safe_fields:
                if k in body:
                    print(f"  {k}: {body[k]}")
    except Exception as e:
        print(f"ERROR: {e}")

    # 2. All entities
    print(f"\n{'=' * 80}")
    print("2. ALL ENTITY TYPES IN WORKSPACE")
    print("=" * 80)
    try:
        from alibabacloud_cms20240330 import models as CmsModels
        from alibabacloud_tea_util import models as UtilModels

        current_time = int(time.time())
        query = ".entity |project __entity_type__, __domain__ |sort __entity_type__"
        req_headers = CmsModels.GetEntityStoreDataHeaders()
        request = CmsModels.GetEntityStoreDataRequest(
            from_=current_time - 600, to=current_time, query=query
        )
        runtime = UtilModels.RuntimeOptions()
        resp = client.get_entity_store_data_with_options(workspace, request, req_headers, runtime)

        if resp.status_code == 200 and resp.body:
            data = resp.body.to_map()
            rows = data.get("data", [])
            headers_list = data.get("header", [])

            print(f"HTTP {resp.status_code}, total entities: {len(rows)}")

            if headers_list and rows:
                try:
                    type_idx = headers_list.index("__entity_type__")
                    domain_idx = headers_list.index("__domain__")
                    types = {}
                    for r in rows:
                        if len(r) > max(type_idx, domain_idx):
                            key = f"{r[domain_idx]}:{r[type_idx]}"
                            types[key] = types.get(key, 0) + 1
                    print(f"\nUnique entity types ({len(types)}):")
                    for t in sorted(types):
                        print(f"  {t} ({types[t]})")
                except Exception as e:
                    print(f"Error parsing: {e}")
    except Exception as e:
        print(f"ERROR: {e}")

    # 3. Devops domain presence check
    print(f"\n{'=' * 80}")
    print("3. DEVOPS DOMAIN CHECK")
    print("=" * 80)
    try:
        from alibabacloud_cms20240330 import models as CmsModels
        from alibabacloud_tea_util import models as UtilModels

        query = ".entity with(domain='devops') |project __entity_type__ |sort __entity_type__"
        req_headers = CmsModels.GetEntityStoreDataHeaders()
        request = CmsModels.GetEntityStoreDataRequest(
            from_=current_time - 600, to=current_time, query=query
        )
        runtime = UtilModels.RuntimeOptions()
        resp = client.get_entity_store_data_with_options(workspace, request, req_headers, runtime)

        if resp.status_code == 200 and resp.body:
            data = resp.body.to_map()
            rows = data.get("data", [])

            print(f"HTTP {resp.status_code}, devops entities: {len(rows)}")

            type_counts = {}
            for r in rows:
                if r:
                    t = r[0]
                    type_counts[t] = type_counts.get(t, 0) + 1

            expected = ["devops.code_repository", "devops.code_release", "devops.image",
                        "devops.image_registry", "devops.developer"]
            for et in expected:
                count = type_counts.get(et, 0)
                status = "PRESENT" if count > 0 else "MISSING"
                print(f"  {status}: {et} ({count})")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
