from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from engine_reference_world import create_plugin
from engine_runtime import (
    EngineApplication,
    LeaseHeldError,
    RuntimeConfig,
    RuntimeLease,
)
from engine_sdk import (
    AutonomyBindingStatusV1,
    AutonomyDecisionKindV1,
    AutonomyDecisionV1,
    CognitionRequestV1,
    CognitionRouteV1,
    ConditionV1,
    ContractError,
    DesiredEffectV1,
    DispatchAttemptStateV1,
    DispatchAttemptV1,
    GoalCandidateV1,
    GoalModeV2,
    GoalSpecV2,
    ProposedActionV1,
    SuggestionV1,
    load_static_manifest,
)

from engine import PluginRegistryV2
from engine.autonomy_v3 import enrollment_resource_keys
from engine.policy_v2 import MandatePolicyV1

PLUGIN = "engine.reference-world"
TARGET = "engine.reference-world.warehouse"
ENTITY = "warehouse:bin:reserve"
FAMILY = "warehouse.transfer-bin"
STRATEGY = "warehouse.reserve-maintainer/v1"
TEMPLATE = "warehouse.reserve-minimum/v1"


def _application(tmp_path: Path, *, plugin=None) -> tuple[EngineApplication, object]:
    actual = plugin or create_plugin(tmp_path / "warehouse.sqlite3")
    registry = PluginRegistryV2()
    registry.register(actual, "plugins/reference-world")
    app = EngineApplication(
        RuntimeConfig(store_path=tmp_path / "engine.sqlite3"), registry=registry
    )
    return app, actual


def _enroll(
    app: EngineApplication,
    *,
    limits: dict | None = None,
    risk_ceiling: str = "low",
    privacy_grants: tuple[str, ...] = (),
    control_existing_goals: bool = False,
):
    with app.lease():
        return app.autonomy_enroll(
            plugin_id=PLUGIN,
            strategy_id=STRATEGY,
            target_ids=(TARGET,),
            entity_ids=(ENTITY,),
            capability_families=(FAMILY,),
            goal_template_ids=(TEMPLATE,),
            limits=(
                limits
                if limits is not None
                else {
                    "reserve_minimum_count": 3,
                    "parameters": {"count": {"max": 10}},
                }
            ),
            risk_ceiling=risk_ceiling,
            privacy_grants=privacy_grants,
            control_existing_goals=control_existing_goals,
            instantiate_goal_templates=True,
        )


def _close(app: EngineApplication, plugin: object) -> None:
    app.close()
    plugin.providers[0].store.close()


def _variant_application(
    tmp_path: Path,
    strategy_type: type,
    *,
    route: str,
    privacy: bool = False,
    specialist: object | None = None,
) -> tuple[EngineApplication, object, object]:
    manifest_text = Path("plugins/reference-world/engine-plugin.toml").read_text(
        encoding="utf-8"
    )
    manifest_text = manifest_text.replace(
        'cognition_route = "deterministic"', f'cognition_route = "{route}"', 1
    )
    if route == "specialist":
        manifest_text = manifest_text.replace(
            f'cognition_route = "{route}"',
            f'cognition_route = "{route}"\n'
            'specialist_id = "engine.reference-world.warehouse-specialist/v1"',
            1,
        )
    if privacy:
        manifest_text = manifest_text.replace(
            "privacy_classes = []", 'privacy_classes = ["sensitive"]', 1
        )
    manifest_path = tmp_path / "engine-plugin.toml"
    manifest_path.write_text(manifest_text, encoding="utf-8")
    manifest = load_static_manifest(manifest_path)
    spec = next(item for item in manifest.autonomy_strategies if item.id == STRATEGY)
    strategy = strategy_type(spec)
    plugin = create_plugin(tmp_path / "warehouse.sqlite3")
    replacements = {"manifest": manifest, "autonomy_strategies": (strategy,)}
    if specialist is not None:
        replacements["specialists"] = (specialist,)
    plugin = replace(plugin, **replacements)
    registry = PluginRegistryV2()
    registry.register(plugin, manifest_path)
    app = EngineApplication(
        RuntimeConfig(store_path=tmp_path / "engine.sqlite3"), registry=registry
    )
    return app, plugin, strategy


def _create_cognition_goal(app: EngineApplication) -> None:
    app.store.create_goal(
        GoalSpecV2(
            id="goal:cognition-fixture",
            source_intent="Exercise a configured autonomy cognition route",
            mode=GoalModeV2.MAINTAIN,
            entity_scope={"target_ids": [TARGET]},
            desired_effects=(
                DesiredEffectV1(
                    id="reserve",
                    capability_family=FAMILY,
                    entity_selector={"entity_ids": [ENTITY]},
                    condition=ConditionV1(
                        "gte", path="observation:bin.count", value=3, unit="crate"
                    ),
                    parameters={"minimum_count": 3},
                ),
            ),
            status="completed",
        )
    )


def test_observe_supervised_and_delegated_share_one_authority_path(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        _enroll(app)
        with app.lease():
            app.heart.run_cycle()
        assert app.store.dispatch_attempts() == ()
        assert app.store.autonomy_bindings()[-1]["status"] is AutonomyBindingStatusV1.SHADOW
        assert app.store.live_goals() == ()

        app.autonomy_mode("supervised")
        with app.lease():
            app.heart.run_cycle()
        pending = app.store.autonomy_bindings()[-1]
        assert pending["status"] is AutonomyBindingStatusV1.PENDING_APPROVAL
        assert app.store.dispatch_attempts() == ()

        with app.lease():
            app.autonomy_proposal_approve(pending["binding"].evaluation_id)
        attempts = app.store.dispatch_attempts()
        assert len(attempts) == 1
        assert attempts[0].autonomy_binding is not None
        assert app.store.brain_call_count() == 0
    finally:
        _close(app, plugin)


def test_yolo_alias_changes_only_mode_and_mode_change_works_during_lease(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        enrollment_count = len(app.store.autonomy_enrollments())
        with app.lease() as lease:
            assert lease.assert_current().endswith(f"g{lease.generation}")
            changed = app.yolo_alias_enable()
            assert changed["mode"] == "delegated"
        assert len(app.store.autonomy_enrollments()) == enrollment_count
        assert app.yolo_alias_disable()["mode"] == "paused"
    finally:
        _close(app, plugin)


def test_lease_generation_is_monotonic_across_clean_shutdown(tmp_path: Path) -> None:
    path = tmp_path / "lease.sqlite3"
    with RuntimeLease(path) as first:
        generation = first.generation
    with RuntimeLease(path) as second:
        assert second.generation == generation + 1


def test_enrollment_rejects_context_and_risk_expansion(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        with app.lease(), pytest.raises(ValueError, match="context expands"):
            app.autonomy_enroll(
                plugin_id=PLUGIN,
                strategy_id=STRATEGY,
                target_ids=(TARGET,),
                entity_ids=(ENTITY,),
                capability_families=(FAMILY,),
                context_plugin_ids=("engine.context",),
            )
        with pytest.raises(ValueError, match="exceeds delegated"):
            _enroll(app, risk_ceiling="read_only")
    finally:
        _close(app, plugin)


def test_enrollment_parameter_limit_is_rechecked_before_io(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        _enroll(
            app,
            limits={
                "reserve_minimum_count": 3,
                "parameters": {"count": {"max": 1}},
            },
        )
        app.autonomy_mode("delegated")
        with app.lease():
            app.heart.run_cycle()
        assert app.store.dispatch_attempts() == ()
        assert plugin.providers[0].store.connection.execute(
            "SELECT COUNT(*) FROM tasks"
        ).fetchone()[0] == 0
    finally:
        _close(app, plugin)


def test_stable_world_is_quiet_and_inflight_attempt_reserves_resource(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        _enroll(app)
        app.autonomy_mode("delegated")
        with app.lease():
            app.heart.run_cycle()  # creates one async task
            first = len(app.store.autonomy_evaluations())
            app.heart.run_cycle()  # recovery/poll owns the reserved resource
            assert len(app.store.autonomy_evaluations()) == first
            app.heart.run_cycle()  # one NOOP after the observed effect changed
            quiet_boundary = len(app.store.autonomy_evaluations())
            app.heart.run_cycle()
            app.heart.run_cycle()
        assert len(app.store.autonomy_evaluations()) == quiet_boundary
        assert app.store.brain_call_count() == 0
    finally:
        _close(app, plugin)


def test_executive_route_calls_once_and_model_failure_defers(tmp_path: Path) -> None:
    class RequestingStrategy:
        id = STRATEGY
        plugin_id = PLUGIN

        def __init__(self, spec):
            self.spec = spec
            self.calls = 0

        def evaluate(self, context):
            self.calls += 1
            return AutonomyDecisionV1(
                AutonomyDecisionKindV1.REQUEST_EXECUTIVE,
                cognition_request=CognitionRequestV1(
                    CognitionRouteV1.EXECUTIVE, "goal:cognition-fixture"
                ),
            )

    class FailingBrain:
        id = "fixture.failing-executive"

        def __init__(self):
            self.calls = 0

        def decide(self, goal, context):
            del goal, context
            self.calls += 1
            raise RuntimeError("model offline")

    app, plugin, strategy = _variant_application(
        tmp_path, RequestingStrategy, route="executive"
    )
    brain = FailingBrain()
    app.heart.brain = brain
    try:
        _enroll(app)
        _create_cognition_goal(app)
        app.autonomy_mode("delegated")
        with app.lease():
            app.heart.run_cycle()
        evaluation = app.store.autonomy_evaluations()[-1]
        assert strategy.calls == 1
        assert brain.calls == 1
        assert evaluation.cognition_calls == 1
        assert evaluation.decision.kind is AutonomyDecisionKindV1.DEFER
        assert "model offline" in evaluation.decision.rationale
        assert app.store.dispatch_attempts() == ()
    finally:
        _close(app, plugin)


def test_recovery_horizon_closes_unknown_and_releases_the_resource(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        _enroll(app)
        stale = datetime.now(UTC) - timedelta(hours=2)
        app.store.save_dispatch_attempt(
            DispatchAttemptV1(
                id="dispatch-attempt:unknown-horizon",
                operation_key="operation:unknown-horizon",
                request_id="request:unknown-horizon",
                authorization_id="authorization:unknown-horizon",
                target_id=TARGET,
                entity_id=ENTITY,
                conflict_domain=FAMILY,
                state=DispatchAttemptStateV1.RECOVERY_REQUIRED,
                prepared_at=stale.isoformat(),
                updated_at=stale.isoformat(),
            )
        )
        with app.lease():
            app.heart.run_cycle()
        closed = next(
            item
            for item in app.store.dispatch_attempts()
            if item.id == "dispatch-attempt:unknown-horizon"
        )
        assert closed.state is DispatchAttemptStateV1.CLOSED_UNKNOWN
        assert app.store.dispatch_attempts(open_only=True) == ()
        listed = app.autonomy_attempts()
        assert any(item["id"] == closed.id for item in listed)
    finally:
        _close(app, plugin)


def test_nonempty_enrollment_budget_is_rejected(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        with pytest.raises(ValueError, match="budget is not enforced"):
            with app.lease():
                app.autonomy_enroll(
                    plugin_id=PLUGIN,
                    strategy_id=STRATEGY,
                    target_ids=(TARGET,),
                    entity_ids=(ENTITY,),
                    capability_families=(FAMILY,),
                    goal_template_ids=(TEMPLATE,),
                    budget={"cycles": 3},
                )
        assert app.store.autonomy_enrollments() == ()
    finally:
        _close(app, plugin)


def test_missing_privacy_grant_is_rejected_at_enroll_time(tmp_path: Path) -> None:
    class CountingStrategy:
        id = STRATEGY
        plugin_id = PLUGIN

        def __init__(self, spec):
            self.spec = spec
            self.calls = 0

        def evaluate(self, context):
            del context
            self.calls += 1
            return AutonomyDecisionV1(AutonomyDecisionKindV1.NOOP)

    app, plugin, strategy = _variant_application(
        tmp_path, CountingStrategy, route="deterministic", privacy=True
    )
    try:
        with pytest.raises(ValueError, match="required privacy grants"):
            _enroll(app, privacy_grants=())
        assert strategy.calls == 0
        assert app.store.autonomy_evaluations() == ()
        assert app.store.brain_call_count() == 0
    finally:
        _close(app, plugin)


@pytest.mark.parametrize(
    "violation",
    ("unknown_template", "cross_plugin", "capability_expansion", "entity_expansion"),
)
def test_strategy_output_cannot_expand_typed_enrollment(
    tmp_path: Path, violation: str
) -> None:
    class ExpandingStrategy:
        id = STRATEGY
        plugin_id = PLUGIN

        def __init__(self, spec):
            self.spec = spec

        def evaluate(self, context):
            if violation in {"unknown_template", "cross_plugin"}:
                candidate = GoalCandidateV1(
                    id="goal-candidate:invalid",
                    plugin_id=("another.plugin" if violation == "cross_plugin" else PLUGIN),
                    template_id=(
                        "warehouse.unknown/v1"
                        if violation == "unknown_template"
                        else TEMPLATE
                    ),
                    target_id=TARGET,
                    entity_ids=(ENTITY,),
                    parameters={"minimum_count": 3},
                    based_on_snapshot_id=context.current_snapshot_id,
                    based_on_world_revision=context.current_world_revision,
                    proposed_by=self.id,
                )
                return AutonomyDecisionV1(
                    AutonomyDecisionKindV1.PROPOSE_GOAL_CANDIDATE,
                    goal_candidate=candidate,
                )
            proposal = ProposedActionV1(
                id="proposal:invalid",
                goal_id="goal:cognition-fixture",
                desired_effect_id="reserve",
                capability_family=(
                    "warehouse.unknown"
                    if violation == "capability_expansion"
                    else FAMILY
                ),
                target_id=TARGET,
                entity_id=(
                    "warehouse:bin:incoming"
                    if violation == "entity_expansion"
                    else ENTITY
                ),
                semantic_parameters={"minimum_count": 3},
                based_on_snapshot_id=context.current_snapshot_id,
                based_on_world_revision=context.current_world_revision,
                proposed_by=self.id,
            )
            return AutonomyDecisionV1(
                AutonomyDecisionKindV1.PROPOSE_EFFECT,
                proposed_action=proposal,
            )

    app, plugin, _strategy = _variant_application(
        tmp_path, ExpandingStrategy, route="deterministic"
    )
    try:
        _enroll(app, control_existing_goals=True)
        _create_cognition_goal(app)
        app.autonomy_mode("delegated")
        with app.lease():
            app.heart.run_cycle()
        assert app.store.autonomy_bindings()[-1]["status"] is AutonomyBindingStatusV1.DEFERRED
        assert app.store.dispatch_attempts() == ()
        assert plugin.providers[0].store.connection.execute(
            "SELECT COUNT(*) FROM tasks"
        ).fetchone()[0] == 0
    finally:
        _close(app, plugin)


def test_fabricated_evidence_cannot_dispatch_in_any_mode(tmp_path: Path) -> None:
    class FabricatingStrategy:
        id = STRATEGY
        plugin_id = PLUGIN

        def __init__(self, spec):
            self.spec = spec

        def evaluate(self, context):
            return AutonomyDecisionV1(
                AutonomyDecisionKindV1.PROPOSE_GOAL_CANDIDATE,
                goal_candidate=GoalCandidateV1(
                    id="goal-candidate:fake",
                    plugin_id=PLUGIN,
                    template_id=TEMPLATE,
                    target_id=TARGET,
                    entity_ids=(ENTITY,),
                    parameters={"minimum_count": 8},
                    based_on_snapshot_id=context.current_snapshot_id,
                    based_on_world_revision=context.current_world_revision,
                    proposed_by=self.id,
                    evidence_ids=("fabricated-evidence",),
                ),
                evidence_ids=("fabricated-evidence",),
            )

    app, plugin, _strategy = _variant_application(
        tmp_path, FabricatingStrategy, route="deterministic"
    )
    try:
        _enroll(app)
        app.autonomy_mode("delegated")
        with app.lease():
            app.heart.run_cycle()
        binding = app.store.autonomy_bindings()[-1]
        assert binding["status"] is AutonomyBindingStatusV1.DEFERRED
        assert "projection" in binding["reason"]
        assert app.store.dispatch_attempts() == ()
    finally:
        _close(app, plugin)


def test_autonomy_decision_cannot_carry_a_free_goal_spec() -> None:
    with pytest.raises(ContractError, match="requires only goal_candidate"):
        AutonomyDecisionV1(AutonomyDecisionKindV1.PROPOSE_GOAL_CANDIDATE)


def test_specialist_receives_only_the_enrolled_projection(tmp_path: Path) -> None:
    class RequestingStrategy:
        id = STRATEGY
        plugin_id = PLUGIN

        def __init__(self, spec):
            self.spec = spec

        def evaluate(self, context):
            del context
            return AutonomyDecisionV1(
                AutonomyDecisionKindV1.REQUEST_SPECIALIST,
                cognition_request=CognitionRequestV1(
                    CognitionRouteV1.SPECIALIST,
                    "goal:cognition-fixture",
                    specialist_id="engine.reference-world.warehouse-specialist/v1",
                ),
            )

    class CapturingSpecialist:
        id = "engine.reference-world.warehouse-specialist/v1"
        plugin_id = PLUGIN
        supported_families = (FAMILY,)

        def __init__(self):
            self.contexts = []

        def advise_autonomy(self, context, request):
            del request
            self.contexts.append(context)
            return AutonomyDecisionV1(AutonomyDecisionKindV1.DEFER)

    specialist = CapturingSpecialist()
    app, plugin, _strategy = _variant_application(
        tmp_path,
        RequestingStrategy,
        route="specialist",
        specialist=specialist,
    )
    try:
        _enroll(app)
        _create_cognition_goal(app)
        app.autonomy_mode("delegated")
        with app.lease():
            app.heart.run_cycle()
        assert len(specialist.contexts) == 1
        projected = specialist.contexts[0].projection
        assert {item["id"] for item in projected["world"]["entities"]} == {ENTITY}
        assert {
            item["entity_id"] for item in projected["world"]["observations"]
        } == {ENTITY}
        assert app.store.autonomy_evaluations()[-1].cognition_calls == 1
        assert app.store.brain_call_count() == 1
        assert app.store.dispatch_attempts() == ()
    finally:
        _close(app, plugin)


def test_overlapping_enrollment_and_revocation_before_io_fail_closed(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        enrollment = _enroll(app)
        with pytest.raises(ValueError, match="overlaps"):
            _enroll(app)
        app.autonomy_mode("delegated")

        class RevokingPolicy(MandatePolicyV1):
            def authorize(self, request, decision, mandate):
                authorization = super().authorize(request, decision, mandate)
                app.autonomy_enrollment_disable(enrollment.id)
                return authorization

        app.heart.policy = RevokingPolicy()
        with app.lease():
            app.heart.run_cycle()
        assert app.store.dispatch_attempts() == ()
        assert app.store.autonomy_bindings()[-1]["status"] is AutonomyBindingStatusV1.DEFERRED
        assert not app.store.get_autonomy_enrollment(enrollment.id).enabled
    finally:
        _close(app, plugin)


def test_expired_enrollment_releases_its_resource_for_reenrollment(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        enrollment = _enroll(app)
        expired = replace(
            enrollment,
            revision=2,
            expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        )
        app.store.save_autonomy_enrollment(
            expired,
            resource_keys=enrollment_resource_keys(app.registry, expired),
        )
        replacement = _enroll(app)
        assert replacement.id != enrollment.id
        current = app.store.get_autonomy_enrollment(enrollment.id)
        assert current.revision == 3
        assert not current.enabled
    finally:
        _close(app, plugin)


def test_expired_authorization_is_rejected_before_executor_call(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        _enroll(app)
        app.autonomy_mode("delegated")

        class ExpiringPolicy(MandatePolicyV1):
            def authorize(self, request, decision, mandate):
                value = super().authorize(request, decision, mandate)
                return replace(
                    value,
                    expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                )

        app.heart.policy = ExpiringPolicy()
        with app.lease():
            app.heart.run_cycle()
        assert app.store.dispatch_attempts() == ()
        assert plugin.providers[0].store.connection.execute(
            "SELECT COUNT(*) FROM tasks"
        ).fetchone()[0] == 0
    finally:
        _close(app, plugin)


def test_newer_observation_between_policy_and_io_defers_dispatch(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        _enroll(app)
        app.autonomy_mode("delegated")

        class ReobservingPolicy(MandatePolicyV1):
            def authorize(self, request, decision, mandate):
                authorization = super().authorize(request, decision, mandate)
                app.observe()
                return authorization

        app.heart.policy = ReobservingPolicy()
        with app.lease():
            app.heart.run_cycle()
        assert app.store.dispatch_attempts() == ()
        assert app.store.autonomy_bindings()[-1]["status"] is AutonomyBindingStatusV1.DEFERRED
        assert plugin.providers[0].store.connection.execute(
            "SELECT COUNT(*) FROM tasks"
        ).fetchone()[0] == 0
    finally:
        _close(app, plugin)


def test_pause_and_lease_loss_before_io_make_zero_executor_calls(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        _enroll(app)
        app.autonomy_mode("delegated")

        class PausingPolicy(MandatePolicyV1):
            def authorize(self, request, decision, mandate):
                authorization = super().authorize(request, decision, mandate)
                app.autonomy_mode("paused")
                return authorization

        app.heart.policy = PausingPolicy()
        with app.lease():
            app.heart.run_cycle()
        assert app.store.dispatch_attempts() == ()

        app.autonomy_mode("delegated")
        app.heart.policy = MandatePolicyV1()
        with app.lease():
            app.heart.set_dispatch_guard(
                lambda: (_ for _ in ()).throw(LeaseHeldError("lost fixture lease"))
            )
            app.heart.run_cycle()
        assert app.store.dispatch_attempts() == ()
        assert plugin.providers[0].store.connection.execute(
            "SELECT COUNT(*) FROM tasks"
        ).fetchone()[0] == 0
    finally:
        _close(app, plugin)


def test_lease_loss_after_durable_attempt_aborts_before_executor_io(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        _enroll(app)
        app.autonomy_mode("delegated")
        fence_calls = 0

        def lose_after_prepare():
            nonlocal fence_calls
            fence_calls += 1
            if fence_calls == 2:
                raise LeaseHeldError("lost after durable prepare")
            return "fixture:g1"

        with app.lease():
            app.heart.set_dispatch_guard(lose_after_prepare)
            app.heart.run_cycle()
        attempt = app.store.dispatch_attempts()[0]
        assert attempt.state is DispatchAttemptStateV1.ABORTED_BEFORE_IO
        assert plugin.providers[0].store.connection.execute(
            "SELECT COUNT(*) FROM tasks"
        ).fetchone()[0] == 0
    finally:
        _close(app, plugin)


def test_pause_allows_inflight_recovery_but_starts_no_new_strategy(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        _enroll(app)
        app.autonomy_mode("delegated")
        with app.lease():
            app.heart.run_cycle()
        evaluations = len(app.store.autonomy_evaluations())
        assert app.store.dispatch_attempts(open_only=True)[0].state is DispatchAttemptStateV1.RECEIPT_RECORDED

        app.autonomy_mode("paused")
        with app.lease():
            app.heart.run_cycle()
        assert len(app.store.autonomy_evaluations()) == evaluations
        assert app.store.dispatch_attempts(open_only=True) == ()
        assert plugin.providers[0].store.connection.execute(
            "SELECT reserve FROM state WHERE id=1"
        ).fetchone()[0] == 3
    finally:
        _close(app, plugin)


def test_changed_supervised_proposal_is_superseded_and_persisted(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        _enroll(app)
        app.autonomy_mode("supervised")
        with app.lease():
            app.heart.run_cycle()
        original = app.store.autonomy_bindings()[-1]
        assert original["status"] is AutonomyBindingStatusV1.PENDING_APPROVAL

        warehouse = plugin.providers[0].store.connection
        warehouse.execute("UPDATE state SET reserve=10 WHERE id=1")
        warehouse.commit()
        with app.lease(), pytest.raises(ValueError, match="review the latest proposal"):
            app.autonomy_proposal_approve(original["binding"].evaluation_id)

        bindings = app.store.autonomy_bindings()
        assert bindings[-2]["status"] is AutonomyBindingStatusV1.SUPERSEDED
        assert bindings[-1]["status"] is AutonomyBindingStatusV1.DEFERRED
        assert app.store.dispatch_attempts() == ()
        with pytest.raises(ValueError, match="only a pending"):
            app.autonomy_proposal_reject(
                original["binding"].evaluation_id, reason="too late"
            )
    finally:
        _close(app, plugin)


def test_crash_after_external_effect_never_blindly_redispatches(tmp_path: Path) -> None:
    plugin = create_plugin(tmp_path / "warehouse.sqlite3")
    inner = plugin.executors[0]

    class CrashAfterEffect:
        id = "warehouse-task-executor"
        plugin_id = PLUGIN

        def __init__(self):
            self.calls = 0

        def dispatch(self, request, authorization):
            self.calls += 1
            receipt = inner.dispatch(request, authorization)
            assert receipt.external_handle
            inner.poll(receipt.external_handle)  # physical/software effect happened
            raise SystemExit("injected process crash before receipt persistence")

        def poll(self, external_handle):
            return inner.poll(external_handle)

        def cancel(self, external_handle):
            return inner.cancel(external_handle)

    crashing = CrashAfterEffect()
    plugin = replace(plugin, executors=(crashing,))
    app, plugin = _application(tmp_path, plugin=plugin)
    _enroll(app)
    app.autonomy_mode("delegated")
    with pytest.raises(SystemExit, match="injected process crash"), app.lease():
        app.heart.run_cycle()
    assert crashing.calls == 1
    assert app.store.dispatch_attempts(open_only=True)[0].state is DispatchAttemptStateV1.PREPARED
    expected_mode = app.store.autonomy_mode()
    expected_enrollments = app.store.autonomy_enrollments(include_history=True)
    expected_evaluations = app.store.autonomy_evaluations()
    expected_bindings = app.store.autonomy_bindings()
    app.close()

    restarted, _ = _application(tmp_path, plugin=plugin)
    try:
        assert restarted.store.autonomy_mode() == expected_mode
        assert restarted.store.autonomy_enrollments(include_history=True) == expected_enrollments
        assert restarted.store.autonomy_evaluations() == expected_evaluations
        assert restarted.store.autonomy_bindings() == expected_bindings
        with restarted.lease():
            restarted.heart.run_cycle()
            restarted.heart.run_cycle()
        assert crashing.calls == 1
        attempt = restarted.store.dispatch_attempts(open_only=True)[0]
        assert attempt.state is DispatchAttemptStateV1.RECOVERY_REQUIRED
    finally:
        _close(restarted, plugin)


def test_suggestions_are_non_operational_and_core_autonomy_is_identity_free(tmp_path: Path) -> None:
    app, plugin = _application(tmp_path)
    try:
        snapshot = app.observe()
        app.store.save_suggestion(
            SuggestionV1(
                "suggestion:1", "fixture-model", "Maybe refill something", snapshot.id
            )
        )
        assert len(app.store.suggestions()) == 1
        assert app.store.live_goals() == ()
        assert app.store.dispatch_attempts() == ()
        sources = "\n".join(
            Path(item).read_text(encoding="utf-8")
            for item in (
                "src/engine/autonomy_v3.py",
                "packages/engine-runtime/src/engine_runtime/application.py",
                "packages/engine-runtime/src/engine_runtime/cli.py",
            )
        )
        for forbidden in ("engine.homey", "engine.reference-world", "warehouse:", "homey:"):
            assert forbidden not in sources
    finally:
        _close(app, plugin)


def test_source_fair_quotas_keep_context_after_442_own_observations() -> None:
    from types import SimpleNamespace

    from engine_sdk import (
        EntityV1,
        EvidenceGrade,
        ObservationV1,
        PrivacyClass,
        WorldSnapshotV2,
    )

    from engine.autonomy_v3 import _project_world

    own = EntityV1(ENTITY, TARGET, "warehouse.bin", PLUGIN)
    context_entities = (
        EntityV1("context:local", "engine.context.local", "context.local", "engine.context"),
        EntityV1(
            "context:location",
            "engine.context.local",
            "context.location",
            "engine.context",
        ),
    )
    observations = [
        ObservationV1(
            f"own:{index}",
            ENTITY,
            "bin.count",
            index,
            PLUGIN,
            "2026-08-14T12:00:00+00:00",
            EvidenceGrade.OBSERVED,
        )
        for index in range(442)
    ]
    observations.extend(
        (
            ObservationV1(
                "sun:el",
                "context:local",
                "sun.elevation_deg",
                32.1,
                "engine.context",
                "2026-08-14T12:00:00+00:00",
                EvidenceGrade.DERIVED,
                unit="degree",
            ),
            ObservationV1(
                "loc:lat",
                "context:location",
                "location.latitude",
                52.37,
                "engine.context",
                "2026-08-14T12:00:00+00:00",
                EvidenceGrade.OBSERVED,
                unit="degree",
            ),
        )
    )
    snapshot = WorldSnapshotV2(
        "world:fair",
        1,
        "2026-08-14T12:00:00+00:00",
        {TARGET: 1, "engine.context.local": 1},
        (own, *context_entities),
        (),
        tuple(observations),
        {},
    )
    enrollment = SimpleNamespace(
        entity_ids=(ENTITY,),
        context_plugin_ids=("engine.context",),
        privacy_grants=(PrivacyClass.LOCAL, PrivacyClass.PUBLIC),
    )
    registry = SimpleNamespace(
        plugin=lambda plugin_id: SimpleNamespace(
            static_manifest=load_static_manifest(Path("plugins/engine-context"))
            if plugin_id == "engine.context"
            else SimpleNamespace(observation_privacy=(), capabilities=())
        )
    )
    entities, projected, truncation = _project_world(enrollment, snapshot, registry)
    properties = {item.property for item in projected}
    assert len([item for item in projected if item.entity_id == ENTITY]) == 442
    assert "sun.elevation_deg" in properties
    assert "location.latitude" not in properties
    assert {item.id for item in entities} >= {ENTITY, "context:local"}
    assert truncation["engine.context"]["truncated_observations"] is False


def test_local_privacy_grant_cannot_expose_latitude() -> None:
    from types import SimpleNamespace

    from engine_sdk import (
        EntityV1,
        EvidenceGrade,
        ObservationV1,
        PrivacyClass,
        WorldSnapshotV2,
    )

    from engine.autonomy_v3 import _project_world, _projected_observation

    entity = EntityV1(
        "context:location",
        "engine.context.local",
        "context.location",
        "engine.context",
    )
    latitude = ObservationV1(
        "lat",
        entity.id,
        "location.latitude",
        52.37,
        "engine.context",
        "2026-08-14T12:00:00+00:00",
        EvidenceGrade.OBSERVED,
    )
    stale_sun = ObservationV1(
        "sun",
        "context:local",
        "sun.elevation_deg",
        10.0,
        "engine.context",
        "2026-08-14T12:00:00+00:00",
        EvidenceGrade.STALE,
    )
    local = EntityV1(
        "context:local", "engine.context.local", "context.local", "engine.context"
    )
    snapshot = WorldSnapshotV2(
        "world:privacy",
        1,
        "2026-08-14T12:00:00+00:00",
        {"engine.context.local": 1},
        (entity, local),
        (),
        (latitude, stale_sun),
        {},
    )
    enrollment = SimpleNamespace(
        entity_ids=("warehouse:bin:reserve",),
        context_plugin_ids=("engine.context",),
        privacy_grants=(PrivacyClass.LOCAL,),
    )
    registry = SimpleNamespace(
        plugin=lambda plugin_id: SimpleNamespace(
            static_manifest=load_static_manifest(Path("plugins/engine-context"))
        )
    )
    _entities, projected, _truncation = _project_world(enrollment, snapshot, registry)
    assert [item.property for item in projected] == ["sun.elevation_deg"]
    payload = _projected_observation(projected[0], enrollment)
    assert payload["evidence_eligible"] is False
