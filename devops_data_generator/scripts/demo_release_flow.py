#!/usr/bin/env python3
"""demo_release_flow.py — 一键制造一次完整的「变更→流水线→发布→部署」事件。

用途：demo / 回归两用。demo 环境图里的数据全是存量，RCA 演示需要"一次变更"；
本脚本在 demo-app 上脚本化执行完整 release flow，让每种边都有真实数据流过。

七幕：
  1. 建分支 feature/change-<ts>，改 k8s/deployment.yaml（replicas 2↔3 + VERSION env）
  2. 提 MR（→ pull_request 实体 + contains/participates 边）
  3. 等 MR 流水线成功（→ pull_request_triggers_pipeline_run 边；
     需要 .gitlab-ci.yml 的 workflow rules 含 merge_request_event，已配）
  4. 合并 MR（main 前进）
  5. 打新 tag（v1.2.0→v1.2.1…自动递增）+ 建 Release（target=main 新 HEAD）
  6. 等 Argo CD auto-sync 到新 commit（→ deployment 新 history + relates_to 边）
  7. 打印验证指引（--verify <tag> 另跑，查 SLS 断言实体/边）

用法（ECS 上，secrets 在 /root/devops-demos/.secrets/）：
  python3 devops_data_generator/scripts/demo_release_flow.py            # 跑全流程
  python3 devops_data_generator/scripts/demo_release_flow.py --verify v1.2.1

依赖：纯标准库。secrets 从文件读（可用环境变量 GITLAB_PAT / ARGOCD_TOKEN 覆盖）。
"""

import argparse
import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

GITLAB = os.environ.get("GITLAB_URL", "http://172.16.0.191:8080")
PROJECT_ID = os.environ.get("GITLAB_PROJECT_ID", "1")
ARGOCD = os.environ.get("ARGOCD_URL",
    "https://nlb-7tgycuz4x6fzm55mpl.cn-hongkong.nlb.aliyuncsslbintl.com:8080")
ARGOCD_APP = os.environ.get("ARGOCD_APP", "demo-app")
SECRETS = os.environ.get("SECRETS_DIR", "/root/devops-demos/.secrets")

# SLS（--verify 用）：从仓库 .env 读
SLS_ENDPOINT = "cn-hongkong.log.aliyuncs.com"
SLS_PROJECT = "default-cms-1819385687343877-cn-hongkong"

GREEN, RED, GRAY = "\033[32m", "\033[31m", "\033[90m"
NC = "\033[0m"


def _read_secret(name, env=""):
    if env and os.environ.get(env):
        return os.environ[env].strip()
    with open(os.path.join(SECRETS, name)) as f:
        return f.read().strip()


def _gl(path, data=None, method=None, pat=""):
    req = urllib.request.Request(
        f"{GITLAB}/api/v4{path}",
        data=json.dumps(data).encode() if data is not None else None,
        headers={"PRIVATE-TOKEN": pat, "Content-Type": "application/json"},
        method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
        return json.loads(body) if body else {}


def _argocd(path, token=""):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(f"{ARGOCD}{path}")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read())


def step(n, msg):
    print(f"\n{GREEN}[幕 {n}]{NC} {msg}", flush=True)


def act1_branch_and_change(pat, ts):
    """建分支 + 改 deployment.yaml（replicas 2↔3 轮换 + VERSION env）。"""
    step(1, "建分支 + 变更 deployment.yaml")
    main = _gl(f"/projects/{PROJECT_ID}/repository/branches/main", pat=pat)
    main_sha = main["commit"]["id"]
    # 文件内容接口返回纯文本（非 JSON），不走 _gl
    req = urllib.request.Request(
        f"{GITLAB}/api/v4/projects/{PROJECT_ID}/repository/files/k8s%2Fdeployment.yaml/raw?ref=main",
        headers={"PRIVATE-TOKEN": pat})
    with urllib.request.urlopen(req, timeout=30) as r:
        content = r.read().decode()
    import re
    m = re.search(r"replicas: (\d+)", content)
    cur = int(m.group(1))
    new = 3 if cur == 2 else 2
    content = content.replace(f"replicas: {cur}", f"replicas: {new}")
    if "VERSION" in content:
        content = re.sub(r'value: "v[^"]*"', f'value: "v{ts}"', content)
    else:
        content = content.replace(
            '        image: curlimages/curl:8.9.1',
            '        image: curlimages/curl:8.9.1\n'
            '        env:\n'
            '        - name: VERSION\n'
            f'          value: "v{ts}"')
    branch = f"feature/change-{ts}"
    _gl(f"/projects/{PROJECT_ID}/repository/commits", {
        "branch": branch,
        "start_branch": "main",
        "commit_message": f"demo: change replicas {cur}->{new}, version v{ts}",
        "actions": [{"action": "update", "file_path": "k8s/deployment.yaml",
                     "content": base64.b64encode(content.encode()).decode(),
                     "encoding": "base64"}],
    }, pat=pat)
    br = _gl(f"/projects/{PROJECT_ID}/repository/branches/{urllib.parse.quote(branch, safe='')}", pat=pat)
    sha = br["commit"]["id"]
    print(f"  分支 {branch} @ {sha[:12]}（replicas {cur}→{new}）")
    return branch, sha, main_sha


def act2_create_mr(pat, branch, ts):
    step(2, "提 MR")
    mr = _gl(f"/projects/{PROJECT_ID}/merge_requests", {
        "source_branch": branch, "target_branch": "main",
        "title": f"demo change v{ts}",
        "description": "demo release flow 自动创建",
    }, pat=pat)
    print(f"  MR !{mr['iid']}（{mr['state']}）")
    return mr


def act3_wait_mr_pipeline(pat, mr_iid, timeout=600):
    step(3, "等 MR 流水线")
    deadline = time.time() + timeout
    while time.time() < deadline:
        pipes = _gl(f"/projects/{PROJECT_ID}/merge_requests/{mr_iid}/pipelines", pat=pat)
        if pipes:
            p = pipes[0]
            if p["status"] == "success":
                print(f"  MR 流水线 #{p['id']} success")
                return p
            if p["status"] in ("failed", "canceled"):
                raise RuntimeError(f"MR 流水线 {p['status']}")
        time.sleep(8)
    raise TimeoutError("MR 流水线超时")


def act4_merge(pat, mr_iid):
    step(4, "合并 MR")
    mr = _gl(f"/projects/{PROJECT_ID}/merge_requests/{mr_iid}/merge", {}, method="PUT", pat=pat)
    print(f"  merged, merge_commit={mr['merge_commit_sha'][:12]}")
    main = _gl(f"/projects/{PROJECT_ID}/repository/branches/main", pat=pat)
    return main["commit"]["id"]


def act5_release(pat, ts, main_sha):
    step(5, "打 tag + 建 Release")
    tags = _gl(f"/projects/{PROJECT_ID}/repository/tags?order_by=version&sort=desc", pat=pat)
    latest = tags[0]["name"] if tags else "v1.0.0"
    parts = latest.lstrip("v").split(".")
    tag = f"v{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
    rel = _gl(f"/projects/{PROJECT_ID}/releases", {
        "tag_name": tag, "ref": main_sha, "name": tag,
        "description": f"demo release flow v{ts}",
    }, pat=pat)
    print(f"  Release {rel['tag_name']} → commit {rel['commit']['id'][:12]}")
    return tag


def act6_wait_argocd(token, main_sha, timeout=600):
    step(6, "等 Argo CD auto-sync（默认轮询 ~3min）")
    deadline = time.time() + timeout
    while time.time() < deadline:
        app = _argocd(f"/api/v1/applications/{ARGOCD_APP}", token=token)
        st = app.get("status", {})
        rev = (st.get("sync") or {}).get("revision", "")
        sync = (st.get("sync") or {}).get("status", "")
        health = (st.get("health") or {}).get("status", "")
        hist = st.get("history") or []
        print(f"  sync={sync} health={health} rev={rev[:8]} history={len(hist)}", flush=True)
        if rev.startswith(main_sha[:8]) and sync == "Synced" and health == "Healthy":
            print(f"  ✅ 已同步到 {main_sha[:12]}")
            return True
        time.sleep(15)
    print("  ⚠️ 超时——Argo CD 还没同步（可在 UI 手动 Sync）")
    return False


def verify(tag):
    """查 SLS：这个 tag 对应的实体/边是否都进图了。"""
    step("V", f"验证 tag={tag} 的图数据（读 SLS）")
    env_file = os.environ.get("DEMO_ENV_FILE",
        "/root/devops-demos/umodel-devops-reference/.env")
    for line in open(env_file):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    try:
        from aliyun.log import LogClient, GetLogsRequest
    except ImportError:
        print("需要 aliyun-log SDK（pip install aliyun-log-python-sdk）")
        sys.exit(2)
    c = LogClient(SLS_ENDPOINT, os.environ["ALIBABA_CLOUD_ACCESS_KEY_ID"],
                  os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"])
    to = int(time.time())
    frm = to - 86400

    def pull(ls, q, line=500):
        r = GetLogsRequest(project=SLS_PROJECT, logstore=SLS_PROJECT + ls,
                           fromTime=frm, toTime=to, query=q, line=line,
                           offset=0, reverse=True)
        return [l.get_contents() for l in c.get_logs(r).get_logs()]

    rels = pull("__entity", '__entity_type__:"devops.release"')
    rel = [r for r in rels if r.get("tag_name") == tag]
    prs = pull("__entity", '__entity_type__:"devops.pull_request"')
    runs = pull("__entity", '__entity_type__:"devops.pipeline_run"')
    deps = pull("__entity", '__entity_type__:"devops.deployment"')

    rel_id = rel[0]["__entity_id__"] if rel else None
    pr_ids = {p["__entity_id__"] for p in prs}
    run_ids = {r["__entity_id__"] for r in runs}
    dep_ids = {d["__entity_id__"] for d in deps}

    def edges_by_dest(dest_type, lt, src_in=None, dest_in=None):
        """__link_type__ 不可索引（只有 __entity_type__/__src/dest_entity_type__
        可索引）——按 dest 类型拉小集合再客户端过滤，避免 * 截断。"""
        rows = pull("__topo", f'__dest_entity_type__:"{dest_type}"')
        n = 0
        for e in rows:
            if (e.get("__link_type__") or e.get("__relation_type__")) != lt:
                continue
            if src_in is not None and e.get("__src_entity_id__") not in src_in:
                continue
            if dest_in is not None and e.get("__dest_entity_id__") not in dest_in:
                continue
            n += 1
        return n

    checks = [
        ("release 实体", bool(rel)),
        ("pull_request 实体", bool(prs)),
        ("pipeline_run 实体", bool(runs)),
        ("deployment 实体", bool(deps)),
        ("边 repository_tags_release",
         edges_by_dest("devops.release", "tags", dest_in={rel_id}) if rel_id else 0),
        ("边 pull_request→triggers→pipeline_run",
         edges_by_dest("devops.pipeline_run", "triggers", src_in=pr_ids, dest_in=run_ids)),
        ("边 release→relates_to→deployment",
         edges_by_dest("devops.deployment", "relates_to", src_in={rel_id}, dest_in=dep_ids) if rel_id else 0),
        ("边 repository→contains→pull_request",
         edges_by_dest("devops.pull_request", "contains", dest_in=pr_ids)),
    ]
    ok = True
    for name, passed in checks:
        mark = f"{GREEN}✅{NC}" if passed else f"{RED}❌{NC}"
        print(f"  {mark} {name}")
        ok = ok and bool(passed)
    print(f"\n{'全部通过' if ok else '有缺项（注意：采集周期 1800s，跑完流程要等下一轮）'}")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", metavar="TAG", help="只验证指定 tag 的图数据")
    args = ap.parse_args()
    if args.verify:
        verify(args.verify)
        return

    pat = _read_secret("gitlab-pat.txt", "GITLAB_PAT")
    token = _read_secret("argocd-producer-token.txt", "ARGOCD_TOKEN")
    ts = time.strftime("%m%d%H%M")

    branch, _sha, _main = act1_branch_and_change(pat, ts)
    mr = act2_create_mr(pat, branch, ts)
    act3_wait_mr_pipeline(pat, mr["iid"])
    main_sha = act4_merge(pat, mr["iid"])
    tag = act5_release(pat, ts, main_sha)
    act6_wait_argocd(token, main_sha)

    print(f"""
{GREEN}剧本跑完{NC}：tag={tag}，main HEAD={main_sha[:12]}
图数据在下个采集周期（1800s）后可见；届时验证：
  python3 devops_data_generator/scripts/demo_release_flow.py --verify {tag}
console 拓扑验证入口：实体探索 → 搜 demo-app / {tag} → 关联拓扑。
""")


if __name__ == "__main__":
    main()
