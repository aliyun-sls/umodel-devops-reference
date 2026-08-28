"""Contract tests for the Yunxiao Flow CI adapter.

Fixtures mirror real responses captured from a live org
(2026-08-28, identifiers anonymized): bare-array pagination, camelCase fields,
run-detail sources nested inside job ``params`` JSON strings.

Run from repo root:
    python -m unittest devops_data_generator.tests.test_yunxiao_flow_adapter -v
"""

import json
import sys
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent          # devops_data_generator/
sys.path.insert(0, str(_PKG))

from adapters.factory import create_ci_adapter  # noqa: E402
from adapters.yunxiao_flow import YunxiaoFlowAdapter  # noqa: E402

ORG = "5f8a1b2c3d4e5f6a7b8c9d00"

PIPELINES = [
    {"createAccountId": "6a0000000000000000000001", "createTime": 1786451118000,
     "pipelineId": 910001, "pipelineName": "demo-release-build"},
    {"createAccountId": "6a0000000000000000000002", "createTime": 1784430216000,
     "pipelineId": 910002, "pipelineName": "demo-deploy-hk"},
]

RUNS = {
    "910001": [
        {"status": "RUNNING", "startTime": 1787800000000, "triggerMode": 3,
         "pipelineRunId": 9, "pipelineId": 910001, "endTime": None,
         "creator": None, "creatorAccountId": "6a0000000000000000000001"},
    ],
    "910002": [
        {"status": "SUCCESS", "startTime": 1784434314000, "triggerMode": 1,
         "pipelineRunId": 4, "pipelineId": 910002, "endTime": 1784434373000,
         "creator": None, "creatorAccountId": "6a0000000000000000000002"},
        {"status": "FAIL", "startTime": 1784432892000, "triggerMode": 6,
         "pipelineRunId": 2, "pipelineId": 910002, "endTime": 1784432930000,
         "creator": None, "creatorAccountId": "6a0000000000000000000002"},
    ],
}

# Real detail shape: sources buried in stages[].stageInfo.jobs[].params (JSON str)
RUN4_DETAIL = {
    "pipelineId": 910002, "pipelineRunId": 4, "status": "SUCCESS",
    "stages": [{
        "name": "部署",
        "stageInfo": {"name": "部署", "status": "SUCCESS", "jobs": [{
            "id": 473712953, "name": "Helm Release部署", "status": "SUCCESS",
            "params": json.dumps({"sources": [{
                "name": "demo-repo_xYPu", "type": "codeup",
                "data": {
                    "commitId": "0123456789abcdef0123456789abcdef01234567",
                    "branch": "main",
                    "projectId": 90001,
                    "repo": "https://codeup.aliyun.com/5f8a1b2c3d4e5f6a7b8c9d00/"
                            "demo-org/demo-repo.git",
                },
            }]}),
        }]},
    }],
}


def _make_adapter(pipelines=None, runs=None, details=None, **overrides) -> YunxiaoFlowAdapter:
    config = {"organization_id": ORG, "personal_access_token": "pt-test",
              "repo_mapping": {"demo-deploy-hk": "90001"}}
    config.update(overrides)
    adapter = YunxiaoFlowAdapter(config)
    pipelines = PIPELINES if pipelines is None else pipelines
    runs = RUNS if runs is None else runs
    details = details or {}

    def fake_get(path: str):
        adapter._paths.append(path)
        if "/runs/" in path:                                   # run detail
            run_id = path.rsplit("/runs/", 1)[1]
            if run_id not in details:
                raise RuntimeError("yunxiao_flow GET ... → HTTP 500: boom")
            return details[run_id]
        if "/runs" in path:                                    # run list
            pid = path.split("/pipelines/")[1].split("/")[0]
            page = int(path.rsplit("page=", 1)[1].split("&")[0])
            return runs.get(pid, []) if page == 1 else []
        # pipeline list: honor pagination for the paging test
        page = int(path.rsplit("page=", 1)[1].split("&")[0])
        per_page = int(path.rsplit("perPage=", 1)[1])
        start = (page - 1) * per_page
        return pipelines[start:start + per_page]

    adapter._paths = []  # type: ignore[attr-defined]
    adapter._get = fake_get  # type: ignore[attr-defined]
    return adapter


class YunxiaoFlowAdapterContractTests(unittest.TestCase):
    def test_provider_name(self):
        self.assertEqual(_make_adapter().get_provider_name(), "yunxiao_flow")

    def test_factory(self):
        a = create_ci_adapter("yunxiao_flow",
                              {"organization_id": "o", "personal_access_token": "t"})
        self.assertIsInstance(a, YunxiaoFlowAdapter)
        with self.assertRaises(ValueError):
            create_ci_adapter("travis", {})

    def test_validate_config_requires_org_and_token(self):
        self.assertFalse(YunxiaoFlowAdapter({}).validate_config())
        self.assertFalse(YunxiaoFlowAdapter(
            {"organization_id": ORG}).validate_config())
        self.assertTrue(_make_adapter().validate_config())

    def test_list_pipelines_maps_definitions(self):
        pipes = _make_adapter().list_pipelines()
        self.assertEqual(len(pipes), 2)
        p = pipes[1]
        self.assertEqual(p["pipeline_id"], "yunxiao_flow:910002")
        self.assertEqual(p["platform_pipeline_id"], "910002")
        self.assertEqual(p["name"], "demo-deploy-hk")
        self.assertEqual(p["data_source"], "yunxiao_flow")
        self.assertEqual(p["repository_id"], "90001")      # repo_mapping 命中
        self.assertEqual(pipes[0]["repository_id"], "")      # 无映射则空
        self.assertEqual(p["url"], "https://flow.aliyun.com/pipelines/910002/current")
        self.assertEqual(p["created_at"], "2026-07-19T03:03:36+00:00")

    def test_list_pipeline_runs_status_and_trigger_mapping(self):
        runs = _make_adapter().list_pipeline_runs()
        self.assertEqual(len(runs), 3)
        by_id = {r["run_id"]: r for r in runs}

        ok = by_id["yunxiao_flow:910002:4"]
        self.assertEqual((ok["status"], ok["conclusion"]), ("success", "success"))
        self.assertEqual(ok["trigger_type"], "manual")       # triggerMode 1
        self.assertEqual(ok["number"], 4)
        self.assertEqual(ok["duration_seconds"], 59)
        self.assertEqual(ok["created_at"], "2026-07-19T04:11:54+00:00")
        self.assertEqual(ok["completed_at"], "2026-07-19T04:12:53+00:00")
        self.assertEqual(ok["triggered_by"], "6a0000000000000000000002")
        self.assertEqual(ok["repository_id"], "90001")     # 沿用 pipeline 映射
        self.assertEqual(ok["commit_sha"], "")               # 未开 detail

        bad = by_id["yunxiao_flow:910002:2"]
        self.assertEqual((bad["status"], bad["conclusion"]), ("failure", "failure"))
        self.assertEqual(bad["trigger_type"], "webhook")     # triggerMode 6

        running = by_id["yunxiao_flow:910001:9"]
        self.assertEqual((running["status"], running["conclusion"]),
                         ("in_progress", ""))
        self.assertEqual(running["trigger_type"], "push")    # triggerMode 3
        self.assertEqual(running["completed_at"], "")
        self.assertEqual(running["duration_seconds"], 0)

    def test_fetch_run_detail_fills_commit_and_repo(self):
        adapter = _make_adapter(fetch_run_detail=True, details={"4": RUN4_DETAIL})
        runs = {r["run_id"]: r for r in adapter.list_pipeline_runs()}
        ok = runs["yunxiao_flow:910002:4"]
        self.assertEqual(ok["commit_sha"],
                         "0123456789abcdef0123456789abcdef01234567")
        self.assertEqual(ok["branch"], "main")
        self.assertEqual(ok["repository_id"], "90001")     # sources.projectId

    def test_run_detail_failure_is_tolerated(self):
        adapter = _make_adapter(fetch_run_detail=True, details={})  # 全 500
        runs = adapter.list_pipeline_runs()
        self.assertEqual(len(runs), 3)
        self.assertTrue(all(r["commit_sha"] == "" for r in runs))

    def test_non_dict_sources_are_skipped(self):
        # 真环境踩出：sources 里可能混字符串元素（git URL 直写）
        detail = {"stages": [{"stageInfo": {"jobs": [{"params": json.dumps({
            "sources": ["https://codeup.aliyun.com/x/y.git",
                        {"data": "not-a-dict"},
                        {"data": {"commitId": "abc123", "projectId": 42,
                                  "branch": "main"}}]})}]}}]}
        adapter = _make_adapter(fetch_run_detail=True,
                                pipelines=[PIPELINES[0]],
                                runs={"910001": RUNS["910001"]},
                                details={"9": detail})
        runs = adapter.list_pipeline_runs()
        self.assertEqual(runs[0]["commit_sha"], "abc123")
        self.assertEqual(runs[0]["repository_id"], "42")

    def test_pagination_follows_until_short_page(self):
        # 31 pipelines → page1(30) + page2(1) then stop
        many = [{"createAccountId": "a", "createTime": 1,
                 "pipelineId": i, "pipelineName": f"p{i}"} for i in range(31)]
        adapter = _make_adapter(pipelines=many, runs={})
        pipes = adapter.list_pipelines()
        self.assertEqual(len(pipes), 31)
        pages = [p for p in adapter._paths if "/runs" not in p]
        self.assertEqual(len(pages), 2)                      # 两页后停止

    def test_max_runs_per_pipeline_caps_output(self):
        adapter = _make_adapter(max_runs_per_pipeline=1)
        runs = adapter.list_pipeline_runs()
        # 每条流水线最多 1 条
        self.assertEqual(len(runs), 2)

    def test_status_matrix(self):
        cases = {"SUCCESS": ("success", "success"),
                 "FAIL": ("failure", "failure"),
                 "RUNNING": ("in_progress", ""),
                 "CANCELED": ("cancelled", "cancelled"),
                 "WAITING": ("queued", ""),
                 "SOMETHING_NEW": ("queued", "")}
        for raw, expected in cases.items():
            with self.subTest(status=raw):
                runs = _make_adapter(
                    pipelines=[PIPELINES[0]],
                    runs={"910001": [{"status": raw, "startTime": 1,
                                       "triggerMode": 1, "pipelineRunId": 1,
                                       "pipelineId": 910001, "endTime": 2,
                                       "creator": None, "creatorAccountId": "a"}]},
                ).list_pipeline_runs()
                self.assertEqual((runs[0]["status"], runs[0]["conclusion"]), expected)


def _detail_with_project(project_id):
    return {"stages": [{"stageInfo": {"jobs": [{"params": json.dumps({
        "sources": [{"data": {"commitId": "c0ffee", "projectId": project_id,
                              "branch": "main"}}]})}]}}]}


class RepoAutoDiscoveryTests(unittest.TestCase):
    """auto_discover_repo: learn definition->repo from the latest run's source."""

    def test_discovers_repository_from_latest_run(self):
        # 910001 无 repo_mapping；其最新 run(9) 详情带 projectId=777000
        adapter = _make_adapter(details={"9": _detail_with_project(777000)})
        pipes = {p["pipeline_id"]: p for p in adapter.list_pipelines()}
        self.assertEqual(pipes["yunxiao_flow:910001"]["repository_id"], "777000")

    def test_repo_mapping_wins_over_discovery(self):
        # 910002 配了映射 90001；即使最新 run 详情说别的，也以映射为准且不探测
        adapter = _make_adapter(details={"4": _detail_with_project(999999)})
        pipes = {p["pipeline_id"]: p for p in adapter.list_pipelines()}
        self.assertEqual(pipes["yunxiao_flow:910002"]["repository_id"], "90001")
        self.assertFalse(any("/pipelines/910002/runs" in p for p in adapter._paths))

    def test_discovery_disabled_means_no_probes(self):
        adapter = _make_adapter(auto_discover_repo=False,
                                details={"9": _detail_with_project(777000)})
        pipes = {p["pipeline_id"]: p for p in adapter.list_pipelines()}
        self.assertEqual(pipes["yunxiao_flow:910001"]["repository_id"], "")
        self.assertFalse(any("/runs" in p for p in adapter._paths))

    def test_pipeline_without_runs_stays_empty(self):
        adapter = _make_adapter(runs={})   # 任何流水线都没有 run
        pipes = adapter.list_pipelines()
        unmapped = [p for p in pipes if p["name"] != "demo-deploy-hk"]
        self.assertTrue(all(p["repository_id"] == "" for p in unmapped))

    def test_discovery_api_failure_is_tolerated(self):
        adapter = _make_adapter(details={})  # detail 全 500
        pipes = {p["pipeline_id"]: p for p in adapter.list_pipelines()}
        self.assertEqual(pipes["yunxiao_flow:910001"]["repository_id"], "")


if __name__ == "__main__":
    unittest.main()
