from __future__ import annotations

import hashlib
import json
import math
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from engine_sdk import SpecialistAdviceV1, SuggestionV1

CELL_ID = "engine.reference-world.warehouse-intent-cell/v1"
MODEL_SCHEMA = "engine.cell-model/v1"
TEMPLATE_ID = "warehouse.reserve-minimum/v1"
DEFER_LABEL = "DEFER"
MAX_INPUT_BYTES = 512
SUPPORTED_LANGUAGES = ("en", "nl")
UNSUPPORTED_MARKERS = {
    "en": (
        " do not ", " don t ", " tell ", " show ", " how ", " why ",
        " simulate ", " rehearse ", " cancel ", " remove ", " disable ",
        " order ", " supplier ", " incoming ", " outbound ", " outgoing ",
        " meeting ", " hotel ", " maybe ", " unlimited ", " report ",
        " explain ", " rewrite ", " train ", " drain ", " empty ",
    ),
    "nl": (
        " niet ", " vertel ", " toon ", " hoeveel ", " waarom ",
        " simuleer ", " oefen ", " annuleer ", " verwijder ", " schakel ",
        " bestel ", " leverancier ", " inkomende ", " uitgaande ",
        " vergader", " hotel", " misschien ", " onbeperkt ", " meld ",
        " leg uit ", " herschrijf ", " train ", " haal ", " leeg ",
    ),
}


class CellArtifactError(ValueError):
    """The local model artifact is unavailable, malformed, or not frozen."""


@dataclass(frozen=True)
class CellInferenceV1:
    cell_id: str
    model_sha256: str | None
    label: str
    supported: bool
    confidence: float
    language: str
    input_sha256: str
    latency_ms: float
    evidence_grade: str = "inferred"
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"[a-zà-ÿ0-9]+", normalized))


def hashed_features(
    text: str,
    language: str,
    *,
    dimensions: int,
) -> dict[int, float]:
    """Stable bounded features shared by offline training and local inference."""
    normalized = normalize_text(text)
    words = normalized.split()
    padded = f"  {normalized}  "
    terms = [f"language:{language}"]
    terms.extend(f"word:{word}" for word in words)
    terms.extend(
        f"bigram:{left}_{right}" for left, right in zip(words, words[1:])
    )
    for width in (3, 4, 5):
        terms.extend(
            f"char:{padded[index:index + width]}"
            for index in range(max(0, len(padded) - width + 1))
        )
    counts: dict[int, float] = {}
    for term in terms:
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        counts[bucket] = counts.get(bucket, 0.0) + sign
    norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    return {index: value / norm for index, value in counts.items()}


def unsupported_reason(text: str, language: str) -> str | None:
    if language not in UNSUPPORTED_MARKERS:
        return "unsupported language"
    bounded = f" {normalize_text(text)} "
    if any(marker in bounded for marker in UNSUPPORTED_MARKERS[language]):
        return "deterministic unsupported-scope marker"
    return None


class QuantizedIntentCell:
    """One-shot, local-only int8 MLP. It has no runtime or authority handles."""

    def __init__(self, model: dict[str, Any], model_sha256: str):
        self.model = model
        self.model_sha256 = model_sha256
        self._validate()

    @classmethod
    def from_path(
        cls, path: str | Path, *, expected_sha256: str
    ) -> "QuantizedIntentCell":
        raw = Path(path).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if not expected_sha256 or actual != expected_sha256:
            raise CellArtifactError("Cell artifact SHA-256 does not match the frozen manifest")
        try:
            model = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CellArtifactError("Cell artifact is not canonical JSON") from exc
        if not isinstance(model, dict):
            raise CellArtifactError("Cell artifact root must be an object")
        return cls(model, actual)

    def _validate(self) -> None:
        if self.model.get("schema") != MODEL_SCHEMA:
            raise CellArtifactError("unsupported Cell model schema")
        if self.model.get("cell_id") != CELL_ID:
            raise CellArtifactError("Cell artifact identity mismatch")
        if self.model.get("positive_label") != TEMPLATE_ID:
            raise CellArtifactError("Cell artifact label is not the installed template")
        dimensions = self.model.get("dimensions")
        hidden_size = self.model.get("hidden_size")
        if (
            isinstance(dimensions, bool)
            or not isinstance(dimensions, int)
            or not 1 <= dimensions <= 4096
            or isinstance(hidden_size, bool)
            or not isinstance(hidden_size, int)
            or not 1 <= hidden_size <= 128
        ):
            raise CellArtifactError("Cell dimensions exceed the bounded runner")
        threshold = self.model.get("threshold")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise CellArtifactError("Cell threshold is malformed")
        if not 0.5 <= float(threshold) <= 0.99:
            raise CellArtifactError("Cell threshold is outside the frozen range")
        q1 = self.model.get("q_weights_1")
        b1 = self.model.get("bias_1")
        q2 = self.model.get("q_weights_2")
        if (
            not isinstance(q1, list)
            or len(q1) != hidden_size
            or any(not isinstance(row, list) or len(row) != dimensions for row in q1)
            or not isinstance(b1, list)
            or len(b1) != hidden_size
            or not isinstance(q2, list)
            or len(q2) != hidden_size
        ):
            raise CellArtifactError("Cell weight shape is malformed")
        integers = (item for row in q1 for item in row)
        if any(isinstance(item, bool) or not isinstance(item, int) or not -127 <= item <= 127 for item in integers):
            raise CellArtifactError("Cell first-layer weights are not int8")
        if any(isinstance(item, bool) or not isinstance(item, int) or not -127 <= item <= 127 for item in q2):
            raise CellArtifactError("Cell output weights are not int8")
        for name in ("scale_1", "scale_2", "bias_2"):
            value = self.model.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CellArtifactError(f"Cell {name} is malformed")

    def infer(self, text: str, language: str) -> CellInferenceV1:
        started = time.perf_counter()
        encoded = text.encode("utf-8")
        input_sha256 = hashlib.sha256(encoded).hexdigest()
        if language not in SUPPORTED_LANGUAGES:
            return self._defer(
                language, input_sha256, started, "unsupported language"
            )
        if not text.strip():
            return self._defer(language, input_sha256, started, "empty input")
        if len(encoded) > MAX_INPUT_BYTES:
            return self._defer(
                language, input_sha256, started, "input exceeds 512 bytes"
            )
        scope_error = unsupported_reason(text, language)
        if scope_error is not None:
            return self._defer(language, input_sha256, started, scope_error)
        dimensions = int(self.model["dimensions"])
        features = hashed_features(text, language, dimensions=dimensions)
        scale_1 = float(self.model["scale_1"])
        hidden = []
        for row, bias in zip(self.model["q_weights_1"], self.model["bias_1"]):
            total = float(bias)
            total += sum(int(row[index]) * scale_1 * value for index, value in features.items())
            hidden.append(math.tanh(total))
        scale_2 = float(self.model["scale_2"])
        logit = float(self.model["bias_2"]) + sum(
            int(weight) * scale_2 * value
            for weight, value in zip(self.model["q_weights_2"], hidden)
        )
        probability = _sigmoid(logit)
        supported = probability >= float(self.model["threshold"])
        return CellInferenceV1(
            cell_id=CELL_ID,
            model_sha256=self.model_sha256,
            label=TEMPLATE_ID if supported else DEFER_LABEL,
            supported=supported,
            confidence=round(probability if supported else 1.0 - probability, 8),
            language=language,
            input_sha256=input_sha256,
            latency_ms=(time.perf_counter() - started) * 1000,
            reason=("within frozen supported scope" if supported else "confidence below frozen threshold"),
        )

    def _defer(
        self,
        language: str,
        input_sha256: str,
        started: float,
        reason: str,
    ) -> CellInferenceV1:
        return CellInferenceV1(
            cell_id=CELL_ID,
            model_sha256=self.model_sha256,
            label=DEFER_LABEL,
            supported=False,
            confidence=1.0,
            language=language,
            input_sha256=input_sha256,
            latency_ms=(time.perf_counter() - started) * 1000,
            reason=reason,
        )


class LazyQuantizedIntentCell:
    """Keep plugin construction inert and convert artifact failure into DEFER."""

    def __init__(self, path: str | Path, expected_sha256: str):
        self.path = Path(path)
        self.expected_sha256 = expected_sha256
        self._runner: QuantizedIntentCell | None = None
        self._load_error: str | None = None

    def infer(self, text: str, language: str) -> CellInferenceV1:
        encoded = text.encode("utf-8")
        started = time.perf_counter()
        if self._runner is None and self._load_error is None:
            try:
                self._runner = QuantizedIntentCell.from_path(
                    self.path, expected_sha256=self.expected_sha256
                )
            except (OSError, CellArtifactError) as exc:
                self._load_error = f"artifact unavailable: {type(exc).__name__}"
        if self._runner is not None:
            return self._runner.infer(text, language)
        return CellInferenceV1(
            cell_id=CELL_ID,
            model_sha256=None,
            label=DEFER_LABEL,
            supported=False,
            confidence=1.0,
            language=language,
            input_sha256=hashlib.sha256(encoded).hexdigest(),
            latency_ms=(time.perf_counter() - started) * 1000,
            reason=self._load_error or "artifact unavailable",
        )


class WarehouseIntentCellSpecialist:
    """SpecialistBrain adapter that can only emit a non-operational suggestion."""

    id = CELL_ID
    plugin_id = "engine.reference-world"
    supported_families = ("warehouse.transfer-bin",)

    def __init__(
        self,
        runner: LazyQuantizedIntentCell | QuantizedIntentCell,
        *,
        installed_template_ids: tuple[str, ...],
    ) -> None:
        self.runner = runner
        self.installed_template_ids = installed_template_ids

    def advise(
        self, goal: Any, snapshot: Any, request: dict[str, object]
    ) -> SpecialistAdviceV1:
        language = str(request.get("language", ""))
        purpose = str(request.get("purpose", ""))
        text = str(getattr(goal, "source_intent", ""))
        if purpose != "shadow_intent_routing":
            inference = _static_defer(text, language, "adapter is shadow-only")
        else:
            inference = self.runner.infer(text, language)
        if inference.supported and inference.label not in self.installed_template_ids:
            inference = CellInferenceV1(
                **{
                    **inference.to_dict(),
                    "label": DEFER_LABEL,
                    "supported": False,
                    "reason": "predicted template is not installed",
                }
            )
        suggestion = SuggestionV1(
            id="suggestion:cell:" + uuid4().hex,
            source=self.id,
            text=(
                f"Shadow Cell suggests installed template {inference.label}."
                if inference.supported
                else f"Shadow Cell deferred: {inference.reason}."
            ),
            based_on_snapshot_id=str(snapshot.id),
            metadata={
                "operational": False,
                "cell_inference": inference.to_dict(),
            },
        )
        return SpecialistAdviceV1(
            specialist_id=self.id,
            supported=inference.supported,
            proposed_action=None,
            summary="Authorityless Engine Cell shadow suggestion",
            metadata={"suggestion": suggestion.to_dict()},
        )


def _static_defer(text: str, language: str, reason: str) -> CellInferenceV1:
    return CellInferenceV1(
        cell_id=CELL_ID,
        model_sha256=None,
        label=DEFER_LABEL,
        supported=False,
        confidence=1.0,
        language=language,
        input_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        latency_ms=0.0,
        reason=reason,
    )


def _sigmoid(value: float) -> float:
    if value >= 0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    direct = math.exp(value)
    return direct / (1.0 + direct)
