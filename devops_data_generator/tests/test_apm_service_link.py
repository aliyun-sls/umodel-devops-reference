"""Contract tests for the apm.service → devops.repository sourced_from edge.

Covers the task logic (mocked logstore read) and — critically — the enrich
integration against the REAL data_mapping.yaml: the apm side must stay the
CMS-native entity id verbatim, the repository side must become the md5 of
the raw primary key, and keep-alive fields must be stamped.

Run from repo root:
    python -m unittest devops_data_generator.tests.test_apm_service_link -v
"""

import hashlib
import sys
import unittest
from pathlib import Path
from unittest import mock

_PKG = Path(__file__).resolve().parent.parent          # devops_data_generator/
_REPO = _PKG.parent
sys.path.insert(0, str(_PKG))

from tasks.apm_service_link_task import ApmServiceSourcedFromRepositoryTask  # noqa: E402
import tasks.apm_service_link_task as apm_task_mod  # noqa: E402
from generator.sls_data_generator import SlsDataGenerator  # noqa: E402


class _FakeSharedContext:
    def __init__(self):
        self._store = {}

    def set_data(self, key, data, data_type, task_name):
        self._store[key] = data
        return True

    def get_data(self, key, default, task_name):
        return self._store.get(key, default)

    def has_data(self, key):
        return key in self._store

    def clear_expired(self):
        pass

    def get_execution_order(self, enabled):
        return enabled


def _make_task(links):
    task = ApmServiceSourcedFromRepositoryTask({
        "links": links,
        "sls": {"endpoint": "x", "access_key_id": "a",
                "access_key_secret": "b", "project": "p",
                "entity_logstore": "ls"},
    })
    task.set_shared_context(_FakeSharedContext())
    return task


class ApmServiceLinkTaskTests(unittest.TestCase):
    def setUp(self):
        # CI runners have no aliyun-log SDK; the task gates on the module's
        # SLS_SDK_AVAILABLE flag. Tests mock _load_apm_services (no real SLS
        # calls), so force the flag on for the duration of each test.
        self._patcher = mock.patch.object(apm_task_mod, "SLS_SDK_AVAILABLE", True)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_edge_shape_with_resolved_service(self):
        task = _make_task([{"service": "sae-order-processor",
                            "repository_id": "7069710"}])
        task._load_apm_services = lambda: {"sae-order-processor": "cms-md5-abc"}
        rels = task.fetch_data()
        self.assertEqual(len(rels), 1)
        r = rels[0]
        self.assertEqual(r["__link_type__"], "sourced_from")
        self.assertEqual(r["__src_entity_id__"], "cms-md5-abc")
        self.assertEqual(r["entity_id"], "cms-md5-abc")
        self.assertEqual(r["repository_id"], "7069710")

    def test_unknown_service_yields_no_edge(self):
        task = _make_task([{"service": "ghost-svc", "repository_id": "7069710"}])
        task._load_apm_services = lambda: {"sae-order-processor": "cms-md5-abc"}
        self.assertEqual(task.fetch_data(), [])

    def test_empty_links_fail_validation(self):
        self.assertFalse(_make_task([]).validate_config())

    def test_no_services_no_edges(self):
        task = _make_task([{"service": "sae-order-processor",
                            "repository_id": "7069710"}])
        task._load_apm_services = lambda: {}
        self.assertEqual(task.fetch_data(), [])


class EnrichIntegrationTests(unittest.TestCase):
    """Against the real data_mapping.yaml — the md5/keep-alive contract."""

    @classmethod
    def setUpClass(cls):
        cls.gen = SlsDataGenerator(str(_REPO / "devops_data_generator/config/data_mapping.yaml"))

    def test_enrich_preserves_apm_id_and_hashes_repo_id(self):
        edge = {
            "__link_type__": "sourced_from",
            "__src_entity_id__": "682e0ea61738545c750fe460e1aecc02",
            "__dest_entity_id__": "7069710",
            "entity_id": "682e0ea61738545c750fe460e1aecc02",
            "repository_id": "7069710",
        }
        out = self.gen.enrich_relationship_data(
            "apm_service_sourced_from_repository", [edge])
        self.assertEqual(len(out), 1)
        r = out[0]
        # apm 侧：CMS 原生 id 原样透传（不许重算）
        self.assertEqual(r["__src_entity_id__"], "682e0ea61738545c750fe460e1aecc02")
        # devops 侧：md5 主键，与 repository 节点 id 一致
        self.assertEqual(r["__dest_entity_id__"],
                         hashlib.md5("7069710".encode()).hexdigest())
        # 图引擎保活四字段
        self.assertEqual(r["__method__"], "Update")
        self.assertEqual(r["__keep_alive_seconds__"], 1800)
        self.assertIn("__last_observed_time__", r)
        # domain/type 补齐
        self.assertEqual(r["__src_entity_type__"], "apm.service")
        self.assertEqual(r["__dest_entity_type__"], "devops.repository")
        self.assertEqual(r["__relation_type__"], "sourced_from")


if __name__ == "__main__":
    unittest.main()
