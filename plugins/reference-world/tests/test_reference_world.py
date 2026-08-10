from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine_reference_world import create_plugin
from engine_sdk import check_plugin, compare_manifests, load_static_manifest


class ReferenceWorldTests(unittest.TestCase):
    def test_factory_is_inert_until_first_observation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="reference-world-") as raw:
            path = Path(raw) / "world.sqlite3"
            plugin = create_plugin(path)
            self.addCleanup(plugin.providers[0].store.close)
            self.assertFalse(path.exists())
            self.assertEqual((), check_plugin(plugin))
            self.assertTrue(path.exists())

    def test_loaded_and_static_manifests_match(self) -> None:
        plugin = create_plugin(":memory:")
        self.addCleanup(plugin.providers[0].store.close)
        static = load_static_manifest(Path(__file__).resolve().parents[1])
        self.assertEqual((), compare_manifests(static, plugin.manifest))


if __name__ == "__main__":
    unittest.main()
