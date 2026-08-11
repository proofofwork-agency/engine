from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine_ntfy.plugin import (
    NtfyConfig,
    NtfyLifecycleObserver,
    _messages,
    load_plugin,
)
from engine_sdk import (
    LifecycleEventV1,
    check_plugin,
    compare_manifests,
    load_static_manifest,
)


def _event(
    sequence: int,
    kind: str,
    payload: dict[str, object],
    *,
    goal_id: str | None = None,
    source: str = "heart.v2",
) -> LifecycleEventV1:
    return LifecycleEventV1(
        sequence=sequence,
        kind=kind,
        source=source,
        payload=payload,
        created_at="2026-08-10T12:00:00+00:00",
        goal_id=goal_id,
    )


class NtfyPluginTests(unittest.TestCase):
    def test_manifest_and_loaded_plugin_conform(self) -> None:
        manifest = load_static_manifest(Path(__file__).resolve().parents[1])
        with patch.dict("os.environ", {}, clear=True):
            plugin = load_plugin()
        self.assertEqual((), compare_manifests(manifest, plugin.manifest))
        self.assertEqual((), check_plugin(plugin))
        self.assertEqual("engine.ntfy", plugin.lifecycle_observers[0].plugin_id)

    def test_config_is_opt_in_and_remote_http_is_rejected(self) -> None:
        self.assertIsNone(NtfyConfig.from_environment({}).topic)
        with self.assertRaisesRegex(ValueError, "require HTTPS"):
            NtfyConfig.from_environment(
                {
                    "ENGINE_NTFY_TOPIC": "pow-job-x",
                    "ENGINE_NTFY_BASE_URL": "http://example.com",
                }
            )

    def test_only_learning_goal_routine_and_model_proposals_are_rendered(self) -> None:
        events = (
            _event(1, "goal_created", {"id": "goal:comfort"}, goal_id="goal:comfort"),
            _event(
                2,
                "routine_behavior_signal",
                {"signal_id": "signal:motion", "candidate_id": None},
                source="engine.homey",
            ),
            _event(
                3,
                "routine_candidate_created",
                {
                    "template_id": "lighting.daily-off/v1",
                    "example_count": 5,
                },
                source="engine.homey",
            ),
            _event(
                4,
                "proposal_created",
                {
                    "proposed_by": "engine.brain.deterministic/v2",
                    "capability_family": "homey.lighting.zone-state",
                },
                goal_id="goal:comfort",
            ),
            _event(
                5,
                "proposal_created",
                {
                    "proposed_by": "engine.brain.model/local/local-gemma-4b",
                    "capability_family": "homey.lighting.zone-state",
                },
                goal_id="goal:comfort",
                source="engine.brain.model/local/local-gemma-4b",
            ),
            _event(
                6,
                "homey_light_changed",
                {"entity_id": "lamp:office", "on": True},
                source="engine.homey",
            ),
        )

        self.assertEqual(
            [
                "Goal toegevoegd: goal:comfort",
                "Routine geleerd: lighting.daily-off/v1 (5 voorbeelden)",
                "LLM-suggestie: homey.lighting.zone-state voor goal:comfort",
            ],
            _messages(events),
        )

    def test_runtime_health_kinds_render_counts_only_and_raw_kinds_stay_out(
        self,
    ) -> None:
        events = (
            _event(1, "runtime_started", {"targets": 2}, source="engine.runtime/v2"),
            _event(
                2,
                "runtime_circuit_open",
                {
                    "consecutive_failures": 5,
                    "exception_type": "OSError",
                    "message": "disk full at /Users/private/path",
                    "backoff_seconds": 16.0,
                },
                source="engine.runtime/v2",
            ),
            _event(
                3,
                "runtime_heartbeat",
                {
                    "at": "2026-08-12T00:00:00+00:00",
                    "cycles": 7,
                    "rows_written": 3100,
                    "rows_confirmed": 40,
                    "store_bytes": 123456789,
                    "open_attempts": 0,
                },
                source="engine.runtime/v2",
            ),
            _event(
                4, "runtime_lease_lost", {"passes": 42}, source="engine.runtime/v2"
            ),
            _event(
                5,
                "runtime_stopped",
                {"passes": 42, "reason": "lease_lost"},
                source="engine.runtime/v2",
            ),
            _event(
                6,
                "cycle_failed",
                {"exception_type": "OSError", "message": "secret detail"},
                source="engine.runtime/v2",
            ),
            _event(
                7,
                "subscription_failed",
                {"target_id": "target:home"},
                source="engine.homey",
            ),
            _event(8, "prune_failed", {"message": "boom"}, source="engine.runtime/v2"),
            _event(
                9,
                "homey_light_changed",
                {"lux": 512, "watt": 13.7, "presence": True},
                source="engine.homey",
            ),
        )

        rendered = _messages(events)

        self.assertEqual(
            [
                "Engine gestart (2 targets)",
                "Engine circuit open na 5 opeenvolgende cyclefouten",
                "Engine hartslag: 7 cycli, 3100 rijen (40 bevestigd), "
                "123 MB store, 0 open acties",
                "Engine runtime-lease verloren; proces stopt voor herstart",
                "Engine gestopt: lease_lost na 42 cycli",
            ],
            rendered,
        )
        joined = "\n".join(rendered)
        self.assertNotIn("512", joined)
        self.assertNotIn("13.7", joined)
        self.assertNotIn("presence", joined)
        self.assertNotIn("disk full", joined)
        self.assertNotIn("/Users/", joined)
        self.assertNotIn("secret", joined)

    def test_post_uses_owner_topic_and_title(self) -> None:
        events = (
            _event(
                1,
                "routine_activated",
                {"routine_id": "routine:office-off"},
                goal_id="goal:routine:office-off",
            ),
        )
        response = MagicMock(status=200)
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        observer = NtfyLifecycleObserver(
            NtfyConfig("https://ntfy.sh", "pow-job-x", "engine", 2.0)
        )
        with patch("engine_ntfy.plugin.request.urlopen", return_value=response) as send:
            observer.observe(events)
        outgoing = send.call_args.args[0]
        self.assertEqual("https://ntfy.sh/pow-job-x", outgoing.full_url)
        self.assertEqual("engine", outgoing.headers["Title"])
        self.assertEqual(
            b"Routine toegevoegd en geactiveerd: routine:office-off",
            outgoing.data,
        )


if __name__ == "__main__":
    unittest.main()
