"""UModel schema 守门校验（CI 门禁）。

校验三件事，任一失败退出码非零：
1. umodel/ 下所有 entity_set / entity_set_link YAML 可被 yaml.safe_load 解析；
2. 文件数量与生成器契约（tools/gen_umodel_yaml.py 的 ENTITIES/LINKS）一致；
3. uploader 的文件识别逻辑能将全部文件判为有效（无静默跳过）。

Run:  python3 tools/verify_umodel.py
"""
import glob
import importlib.util
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_generator_contract():
    spec = importlib.util.spec_from_file_location(
        "gen_umodel_yaml", os.path.join(ROOT, "tools", "gen_umodel_yaml.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return len(mod.ENTITIES), len(mod.LINKS)


def main() -> int:
    failed = False

    # 1) 全量可解析
    groups = {
        "entity_set": sorted(glob.glob(os.path.join(ROOT, "umodel", "entity_set", "*.yaml"))),
        "entity_set_link": sorted(glob.glob(os.path.join(ROOT, "umodel", "entity_set_link", "*.yaml"))),
    }
    parsed = {}
    for grp, files in groups.items():
        bad = []
        for fp in files:
            try:
                with open(fp, encoding="utf-8") as f:
                    yaml.safe_load(f)
            except Exception as e:  # noqa: BLE001
                bad.append((fp, e))
        parsed[grp] = len(files)
        if bad:
            failed = True
            print(f"❌ {grp}: {len(files) - len(bad)}/{len(files)} 可解析，坏文件:")
            for fp, e in bad:
                print(f"   - {os.path.basename(fp)}: {e}")
        else:
            print(f"✅ {grp}: {len(files)}/{len(files)} 可解析")

    # 2) 与生成器契约数量一致
    n_entities, n_links = load_generator_contract()
    if parsed["entity_set"] != n_entities:
        failed = True
        print(f"❌ entity_set 数量 {parsed['entity_set']} 与生成器契约 {n_entities} 不一致")
    else:
        print(f"✅ entity_set 数量与契约一致: {n_entities}")
    if parsed["entity_set_link"] != n_links:
        failed = True
        print(f"❌ entity_set_link 数量 {parsed['entity_set_link']} 与生成器契约 {n_links} 不一致")
    else:
        print(f"✅ entity_set_link 数量与契约一致: {n_links}")

    # 3) uploader 识别无静默跳过（绕过需要凭据的 client 初始化）
    sys.path.insert(0, ROOT)
    from umodel_uploader.umodel_batch_uploader import UModelBatchUploader

    uploader = UModelBatchUploader.__new__(UModelBatchUploader)
    uploader.endpoint = ""
    uploader.workspace = None
    uploader.client = None
    for grp, files in groups.items():
        uploader.scan_directory(os.path.dirname(files[0]))
        if uploader.last_invalid_files:
            failed = True
            print(f"❌ uploader 无法识别 {len(uploader.last_invalid_files)} 个 {grp} 文件:")
            for fp in uploader.last_invalid_files:
                print(f"   - {os.path.basename(fp)}")
        else:
            print(f"✅ uploader 可识别全部 {len(files)} 个 {grp} 文件")

    if failed:
        print("\n❌ UModel 校验未通过")
        return 1
    print("\n✅ UModel 校验全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
