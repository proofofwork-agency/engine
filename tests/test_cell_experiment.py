from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from engine_sdk import SuggestionV1

from engine.world_store import WorldStore

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cell_candidate import (
    CELL_ID,
    DEFER_LABEL,
    MAX_INPUT_BYTES,
    TEMPLATE_ID,
    CellArtifactError,
    QuantizedIntentCell,
    WarehouseIntentCellSpecialist,
)
from tools.run_cell_experiment import audit_splits

EXPERIMENT = ROOT / "artifacts/experiments/EXP-2026-003-engine-cell-intent"
MODEL = EXPERIMENT / "model.json"


def _runner() -> QuantizedIntentCell:
    expected = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    return QuantizedIntentCell.from_path(MODEL, expected_sha256=expected)


def test_rejected_cell_artifact_is_reconstructible_and_bounded(tmp_path: Path) -> None:
    runner = _runner()
    supported = runner.infer("Keep the reserve bin at four crates.", "en")
    assert supported.label == TEMPLATE_ID
    assert supported.supported is True
    assert supported.evidence_grade == "inferred"

    out_of_scope = runner.infer(
        "Simulate topping up emergency stock to three crates.", "en"
    )
    assert out_of_scope.label == DEFER_LABEL
    assert out_of_scope.supported is False
    assert "unsupported-scope" in out_of_scope.reason
    assert runner.infer("Keep four crates in reserve.", "fr").label == DEFER_LABEL
    assert runner.infer("x" * (MAX_INPUT_BYTES + 1), "en").label == DEFER_LABEL

    tampered = tmp_path / "model.json"
    tampered.write_bytes(MODEL.read_bytes() + b"\n")
    with pytest.raises(CellArtifactError, match="SHA-256"):
        QuantizedIntentCell.from_path(
            tampered,
            expected_sha256=hashlib.sha256(MODEL.read_bytes()).hexdigest(),
        )


def test_candidate_adapter_can_only_return_an_inert_suggestion(tmp_path: Path) -> None:
    adapter = WarehouseIntentCellSpecialist(
        _runner(), installed_template_ids=(TEMPLATE_ID,)
    )
    advice = adapter.advise(
        SimpleNamespace(source_intent="Keep the reserve bin at four crates."),
        SimpleNamespace(id="snapshot:cell-shadow"),
        {"purpose": "shadow_intent_routing", "language": "en"},
    )
    assert advice.specialist_id == CELL_ID
    assert advice.proposed_action is None
    suggestion = SuggestionV1.from_dict(advice.metadata["suggestion"])
    assert suggestion.source == CELL_ID
    assert suggestion.based_on_snapshot_id == "snapshot:cell-shadow"
    assert suggestion.metadata["operational"] is False
    assert suggestion.metadata["cell_inference"]["evidence_grade"] == "inferred"

    store = WorldStore(tmp_path / "shadow.sqlite3")
    try:
        store.save_suggestion(suggestion)
        assert store.suggestions() == (suggestion,)
        assert store.live_goals() == ()
        assert store.mandates() == ()
        assert store.dispatch_attempts() == ()
    finally:
        store.close()

    production_sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "plugins/reference-world/engine-plugin.toml",
            "plugins/reference-world/src/engine_reference_world/plugin.py",
        )
    )
    assert CELL_ID not in production_sources
    assert "warehouse_intent_cell_v1.json" not in production_sources


def test_heldout_no_go_and_split_seal_are_durable() -> None:
    audit = audit_splits()
    assert audit["status"] == "passed"
    assert (
        audit["sha256"]["heldout"]
        == "e9a92f500cb40db16a92e0ba85fbf7bcd0e4656b39f00ffe735c7e4a0ee3a5ed"
    )
    result = json.loads((EXPERIMENT / "heldout-result.json").read_text())
    assert result["release_gate"] == {
        "language_gates_passed": False,
        "passed": False,
        "resource_gates_passed": True,
    }
    assert result["evaluation"]["gates"]["en"]["improvement_at_least_0_03"] is True
    assert result["evaluation"]["gates"]["nl"]["improvement_at_least_0_03"] is False
    assert result["evaluation"]["gates"]["nl"]["cell_improvement"] == 0.0
    assert result["model_sha256"] == hashlib.sha256(MODEL.read_bytes()).hexdigest()
