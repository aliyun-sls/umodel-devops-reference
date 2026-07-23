"""Baseline regression tests for the Phase 1 fixes.

Run from devops_data_generator/:

    python -m unittest discover tests -v

These tests deliberately avoid live SDK / credential dependencies: they cover
the pure-logic relationship tasks, the static-topo keep-alive field, and the
schema generator's link names. Tasks that need a git adapter or live APIs are
out of scope here (future adapter integration tests).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make 'tasks' (and siblings) importable when run from the package dir, and
# the schema generator importable from <repo>/tools/.
_PKG = Path(__file__).resolve().parent.parent          # devops_data_generator/
_REPO = _PKG.parent                                      # repo root
sys.path.insert(0, str(_PKG))
sys.path.insert(0, str(_REPO / "tools"))

import yaml  # noqa: E402  (PyYAML is a runtime dep of config_loader)

from tasks.release_contains_artifact_task import ReleaseContainsArtifactTask  # noqa: E402
from tasks.user_owns_repository_task import (  # noqa: E402
    OWNS_ACCESS_LEVEL_THRESHOLD,
    UserOwnsRepositoryTask,
)
from tasks.static_topo_task import StaticTopoTask  # noqa: E402
import gen_umodel_yaml  # noqa: E402


class FakeSharedContext:
    """Minimal SharedDataContext stand-in: an in-memory dict store."""

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


def _attach(task):
    ctx = FakeSharedContext()
    task.set_shared_context(ctx)
    return ctx


class ReleaseContainsMappingTests(unittest.TestCase):
    """release→artifact must not cross-link different repos sharing a tag."""

    def setUp(self):
        self._orig_mapping_file = ReleaseContainsArtifactTask._MAPPING_FILE

    def tearDown(self):
        ReleaseContainsArtifactTask._MAPPING_FILE = self._orig_mapping_file

    def _write_mapping(self, mappings):
        fh = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        yaml.safe_dump({"repo_image_mappings": mappings}, fh)
        fh.close()
        return fh.name

    def test_mapping_loader_returns_empty_for_template_file(self):
        # The shipped repo_image_mapping.yaml is a placeholder template; the
        # loader skips <...> placeholders and returns {} so matching falls back
        # to per-tag behaviour.
        t = ReleaseContainsArtifactTask({})
        self.assertEqual(t._load_repo_registry_mapping(), {})

    def test_no_crosslink_when_mapping_scopes_registry(self):
        # Two repos share tag v1.0.0 but map to different ACR registries.
        t = ReleaseContainsArtifactTask({})
        ctx = _attach(t)
        ReleaseContainsArtifactTask._MAPPING_FILE = Path(
            self._write_mapping({
                "group/repo-a": "reg-a.local",
                "group/repo-b": "reg-b.local",
            })
        )
        ctx.set_data("repository_raw_data", [
            {"repository_id": "1", "full_path": "group/repo-a"},
            {"repository_id": "2", "full_path": "group/repo-b"},
        ], "entity", "repository")
        ctx.set_data("release_list", [
            {"release_id": "r:1/v1.0.0", "repository_id": "1", "tag_name": "v1.0.0"},
        ], "entity", "release")
        ctx.set_data("artifact_raw_data", [
            {"artifact_id": "acr:img1:artifact:v1.0.0", "tag_name": "v1.0.0",
             "registry": "reg-a.local"},
            {"artifact_id": "acr:img2:artifact:v1.0.0", "tag_name": "v1.0.0",
             "registry": "reg-b.local"},
        ], "entity", "docker_image")
        rels = t.fetch_data()
        dest_ids = {r["__dest_entity_id__"] for r in rels}
        # repo A's release must match only reg-a's artifact, never reg-b's.
        self.assertEqual(dest_ids, {"acr:img1:artifact:v1.0.0"})

    def test_falls_back_to_tag_match_without_mapping(self):
        # No mapping configured -> historical per-tag behaviour (all same-tag
        # artifacts match).
        t = ReleaseContainsArtifactTask({})
        ctx = _attach(t)
        ReleaseContainsArtifactTask._MAPPING_FILE = Path(
            self._write_mapping({})
        )
        ctx.set_data("repository_raw_data", [], "entity", "repository")
        ctx.set_data("release_list", [
            {"release_id": "r:1/v1.0.0", "repository_id": "1", "tag_name": "v1.0.0"},
        ], "entity", "release")
        ctx.set_data("artifact_raw_data", [
            {"artifact_id": "acr:img1:artifact:v1.0.0", "tag_name": "v1.0.0",
             "registry": "reg-a"},
            {"artifact_id": "acr:img2:artifact:v1.0.0", "tag_name": "v1.0.0",
             "registry": "reg-b"},
        ], "entity", "docker_image")
        rels = t.fetch_data()
        self.assertEqual(len(rels), 2)


class OwnsThresholdTests(unittest.TestCase):
    """owns edges must only be emitted for access_level >= 40."""

    def test_threshold_is_40(self):
        self.assertEqual(OWNS_ACCESS_LEVEL_THRESHOLD, 40)

    def test_guest_below_threshold_gets_no_owns_edge(self):
        t = UserOwnsRepositoryTask({})
        ctx = _attach(t)
        ctx.set_data("devops.user_raw_data", [
            {"user_id": "u:guest", "repositories": [
                {"repository_id": "r:1", "access_level": 10, "role": "guest"}]},
            {"user_id": "u:maint", "repositories": [
                {"repository_id": "r:1", "access_level": 40, "role": "maintainer"}]},
        ], "entity", "user")
        rels = t.fetch_data()
        owners = {r["__src_entity_id__"] for r in rels}
        self.assertIn("u:maint", owners)
        self.assertNotIn("u:guest", owners)


class StaticTopoKeepAliveTests(unittest.TestCase):
    """Static relationship records must carry __keep_alive_seconds__ to enter the CMS graph."""

    def test_static_relation_has_keep_alive(self):
        t = StaticTopoTask({"static_topo_config": "/nonexistent-for-test.yaml"})
        _attach(t)
        topo_def = {"relationship_type": "static_link", "relations": [
            {"source_entity_id": "s1", "target_entity_id": "d1"},
        ]}
        rels = t._process_static_relationships(topo_def)
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0].get("__keep_alive_seconds__"), "600")


class GenUmodelMetricLinkTests(unittest.TestCase):
    """The two metric links must not use the self-contradictory devops.*.devops.metric prefix."""

    def test_metric_link_names_are_well_formed(self):
        names = [ln for (_, ln, _, _, _, _) in gen_umodel_yaml.LINKS]
        self.assertIn("devops.user_related_to_metric.user_commit", names)
        self.assertIn(
            "devops.user_related_to_metric.user_project_participation", names
        )
        self.assertNotIn(
            "devops.user_related_to_devops.metric.user_commit", names
        )


if __name__ == "__main__":
    unittest.main()
