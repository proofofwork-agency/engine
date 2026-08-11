#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import statistics
import subprocess
import sys
import time
import tracemalloc
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cell_candidate import (  # noqa: E402 - support direct script execution
    CELL_ID,
    DEFER_LABEL,
    MAX_INPUT_BYTES,
    MODEL_SCHEMA,
    TEMPLATE_ID,
    QuantizedIntentCell,
    hashed_features,
    normalize_text,
    unsupported_reason,
)

EXPERIMENT = ROOT / "artifacts/experiments/EXP-2026-003-engine-cell-intent"
DATA = EXPERIMENT / "data"
DIMENSIONS = 384
HIDDEN_SIZE = 16
EPOCHS = 240
LEARNING_RATE = 0.04
L2 = 0.0001
POSITIVE_CLASS_WEIGHT = 2.0
SEED = 20260811
THRESHOLDS = tuple(round(0.50 + index * 0.05, 2) for index in range(9))
LANGUAGES = ("en", "nl")


@dataclass(frozen=True)
class Example:
    group_id: str
    language: str
    text: str
    label: str

    @property
    def target(self) -> int:
        return int(self.label == TEMPLATE_ID)


def read_examples(path: Path) -> tuple[Example, ...]:
    examples = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            raw = json.loads(line)
            example = Example(
                group_id=str(raw["group_id"]),
                language=str(raw["language"]),
                text=str(raw["text"]),
                label=str(raw["label"]),
            )
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path}:{line_number}: malformed example") from exc
        if example.language not in LANGUAGES:
            raise ValueError(f"{path}:{line_number}: unsupported language")
        if example.label not in {TEMPLATE_ID, DEFER_LABEL}:
            raise ValueError(f"{path}:{line_number}: unsupported label")
        if not example.text.strip() or len(example.text.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError(f"{path}:{line_number}: invalid text size")
        examples.append(example)
    return tuple(examples)


def audit_splits() -> dict[str, object]:
    splits = {name: read_examples(DATA / f"{name}.jsonl") for name in ("train", "dev", "heldout")}
    seen_groups: dict[str, str] = {}
    seen_text: dict[str, str] = {}
    counts: dict[str, object] = {}
    for split, examples in splits.items():
        balance = Counter((item.language, item.label) for item in examples)
        counts[split] = {
            f"{language}:{label}": balance[(language, label)]
            for language in LANGUAGES
            for label in (TEMPLATE_ID, DEFER_LABEL)
        }
        for item in examples:
            previous = seen_groups.setdefault(item.group_id, split)
            if previous != split:
                raise ValueError(f"group leakage: {item.group_id}: {previous}/{split}")
            normalized = normalize_text(item.text)
            previous_text = seen_text.setdefault(normalized, split)
            if previous_text != split:
                raise ValueError(f"normalized text leakage: {item.text!r}")
        groups = Counter(item.group_id for item in examples)
        if any(count != 2 for count in groups.values()):
            raise ValueError(f"{split}: each EN/NL group must contain exactly two examples")
        for group_id in groups:
            pair = [item for item in examples if item.group_id == group_id]
            if {item.language for item in pair} != set(LANGUAGES):
                raise ValueError(f"{split}:{group_id}: missing language counterpart")
            if len({item.label for item in pair}) != 1:
                raise ValueError(f"{split}:{group_id}: translations disagree on label")
    return {
        "status": "passed",
        "counts": counts,
        "sha256": {name: sha256_file(DATA / f"{name}.jsonl") for name in splits},
    }


class RuleBaseline:
    _number = {
        "en": {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"},
        "nl": {"een", "twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen", "tien"},
    }
    _actions = {
        "en": {"keep", "maintain", "refill", "replenish", "restore"},
        "nl": {"houd", "behoud", "vul", "herstel"},
    }
    _entities = {
        "en": {"reserve", "buffer", "backup", "spare"},
        "nl": {"reserve", "buffer", "backup", "reservevoorraad", "reservebak"},
    }
    def predict(self, example: Example) -> str:
        normalized = normalize_text(example.text)
        words = set(normalized.split())
        has_number = any(word.isdigit() and 1 <= int(word) <= 10 for word in words) or bool(words & self._number[example.language])
        rejected = unsupported_reason(example.text, example.language) is not None
        supported = (
            not rejected
            and has_number
            and bool(words & self._actions[example.language])
            and bool(words & self._entities[example.language])
        )
        return TEMPLATE_ID if supported else DEFER_LABEL


class NaiveBayesBaseline:
    def __init__(self) -> None:
        self.class_counts = Counter()
        self.token_counts: dict[int, Counter[str]] = {0: Counter(), 1: Counter()}
        self.totals = Counter()
        self.vocabulary: set[str] = set()

    def fit(self, examples: tuple[Example, ...]) -> None:
        for item in examples:
            target = item.target
            self.class_counts[target] += 1
            tokens = normalize_text(item.text).split()
            self.token_counts[target].update(tokens)
            self.totals[target] += len(tokens)
            self.vocabulary.update(tokens)

    def probability(self, example: Example) -> float:
        total_examples = sum(self.class_counts.values())
        vocabulary_size = len(self.vocabulary)
        scores = {}
        for target in (0, 1):
            score = math.log((self.class_counts[target] + 1) / (total_examples + 2))
            denominator = self.totals[target] + vocabulary_size
            for token in normalize_text(example.text).split():
                score += math.log((self.token_counts[target][token] + 1) / denominator)
            scores[target] = score
        peak = max(scores.values())
        positive = math.exp(scores[1] - peak)
        negative = math.exp(scores[0] - peak)
        return positive / (positive + negative)


def train_mlp(examples: tuple[Example, ...]) -> tuple[list[list[float]], list[float], list[float], float]:
    randomizer = random.Random(SEED)
    radius_1 = math.sqrt(6.0 / (DIMENSIONS + HIDDEN_SIZE))
    radius_2 = math.sqrt(6.0 / (HIDDEN_SIZE + 1))
    weights_1 = [[randomizer.uniform(-radius_1, radius_1) for _ in range(DIMENSIONS)] for _ in range(HIDDEN_SIZE)]
    bias_1 = [0.0] * HIDDEN_SIZE
    weights_2 = [randomizer.uniform(-radius_2, radius_2) for _ in range(HIDDEN_SIZE)]
    bias_2 = 0.0
    features = [hashed_features(item.text, item.language, dimensions=DIMENSIONS) for item in examples]
    order = list(range(len(examples)))
    for epoch in range(EPOCHS):
        randomizer.shuffle(order)
        rate = LEARNING_RATE * (1.0 - 0.65 * epoch / EPOCHS)
        for index in order:
            item = examples[index]
            vector = features[index]
            hidden = [
                math.tanh(bias + sum(row[position] * value for position, value in vector.items()))
                for row, bias in zip(weights_1, bias_1)
            ]
            logit = bias_2 + sum(weight * value for weight, value in zip(weights_2, hidden))
            probability = sigmoid(logit)
            output_error = (probability - item.target) * (
                POSITIVE_CLASS_WEIGHT if item.target else 1.0
            )
            previous_output = list(weights_2)
            for unit in range(HIDDEN_SIZE):
                weights_2[unit] -= rate * (output_error * hidden[unit] + L2 * weights_2[unit])
            bias_2 -= rate * output_error
            for unit in range(HIDDEN_SIZE):
                hidden_error = output_error * previous_output[unit] * (1.0 - hidden[unit] ** 2)
                for position, value in vector.items():
                    weights_1[unit][position] -= rate * (
                        hidden_error * value + L2 * weights_1[unit][position]
                    )
                bias_1[unit] -= rate * hidden_error
    return weights_1, bias_1, weights_2, bias_2


def quantize(values: list[float] | list[list[float]]) -> tuple[Any, float]:
    flat = values if values and isinstance(values[0], float) else [item for row in values for item in row]  # type: ignore[index]
    scale = max(abs(float(item)) for item in flat) / 127.0 or 1.0
    if values and isinstance(values[0], list):
        result = [[max(-127, min(127, round(float(item) / scale))) for item in row] for row in values]  # type: ignore[union-attr]
    else:
        result = [max(-127, min(127, round(float(item) / scale))) for item in values]  # type: ignore[arg-type]
    return result, scale


def build_model(train: tuple[Example, ...], dev: tuple[Example, ...]) -> dict[str, object]:
    weights_1, bias_1, weights_2, bias_2 = train_mlp(train)
    quantized_1, scale_1 = quantize(weights_1)
    quantized_2, scale_2 = quantize(weights_2)
    base = {
        "schema": MODEL_SCHEMA,
        "cell_id": CELL_ID,
        "positive_label": TEMPLATE_ID,
        "dimensions": DIMENSIONS,
        "hidden_size": HIDDEN_SIZE,
        "q_weights_1": quantized_1,
        "scale_1": scale_1,
        "bias_1": bias_1,
        "q_weights_2": quantized_2,
        "scale_2": scale_2,
        "bias_2": bias_2,
        "threshold": 0.5,
        "training": {
            "seed": SEED,
            "epochs": EPOCHS,
            "learning_rate": LEARNING_RATE,
            "l2": L2,
            "positive_class_weight": POSITIVE_CLASS_WEIGHT,
            "train_sha256": sha256_file(DATA / "train.jsonl"),
            "dev_sha256": sha256_file(DATA / "dev.jsonl"),
            "data_provenance": "repository-authored CC0-1.0",
            "external_data": False,
        },
    }
    raw = canonical_json(base)
    runner = QuantizedIntentCell(json.loads(raw), hashlib.sha256(raw.encode()).hexdigest())
    selected = select_threshold(runner, dev)
    base["threshold"] = selected["threshold"]
    base["development_selection"] = selected
    return base


def select_threshold(runner: QuantizedIntentCell, dev: tuple[Example, ...]) -> dict[str, object]:
    probabilities = [(item, positive_probability(runner, item)) for item in dev]
    candidates = []
    for threshold in THRESHOLDS:
        metrics = evaluate_predictions(
            dev,
            [TEMPLATE_ID if probability >= threshold else DEFER_LABEL for _, probability in probabilities],
        )
        if all(float(metrics[language]["defer_recall"]) >= 0.95 for language in LANGUAGES):
            candidates.append((
                min(float(metrics[language]["macro_f1"]) for language in LANGUAGES),
                statistics.mean(float(metrics[language]["macro_f1"]) for language in LANGUAGES),
                threshold,
                metrics,
            ))
    if not candidates:
        threshold = max(THRESHOLDS)
        metrics = evaluate_predictions(
            dev,
            [TEMPLATE_ID if probability >= threshold else DEFER_LABEL for _, probability in probabilities],
        )
        return {"threshold": threshold, "metrics": metrics, "constraint_met": False}
    _, _, threshold, metrics = max(candidates, key=lambda item: (item[0], item[1], item[2]))
    return {"threshold": threshold, "metrics": metrics, "constraint_met": True}


def select_nb_threshold(model: NaiveBayesBaseline, dev: tuple[Example, ...]) -> dict[str, object]:
    probabilities = [model.probability(item) for item in dev]
    candidates = []
    for threshold in THRESHOLDS:
        predictions = [TEMPLATE_ID if value >= threshold else DEFER_LABEL for value in probabilities]
        metrics = evaluate_predictions(dev, predictions)
        candidates.append((
            min(float(metrics[language]["macro_f1"]) for language in LANGUAGES),
            statistics.mean(float(metrics[language]["macro_f1"]) for language in LANGUAGES),
            threshold,
            metrics,
        ))
    _, _, threshold, metrics = max(candidates, key=lambda item: (item[0], item[1], item[2]))
    return {"threshold": threshold, "metrics": metrics}


def positive_probability(runner: QuantizedIntentCell, example: Example) -> float:
    original = runner.model["threshold"]
    runner.model["threshold"] = 0.5
    inference = runner.infer(example.text, example.language)
    runner.model["threshold"] = original
    return inference.confidence if inference.supported else 1.0 - inference.confidence


def evaluate_predictions(examples: tuple[Example, ...], predictions: list[str]) -> dict[str, dict[str, object]]:
    result = {}
    for language in LANGUAGES:
        selected = [(item, prediction) for item, prediction in zip(examples, predictions) if item.language == language]
        tp = sum(item.label == TEMPLATE_ID and prediction == TEMPLATE_ID for item, prediction in selected)
        tn = sum(item.label == DEFER_LABEL and prediction == DEFER_LABEL for item, prediction in selected)
        fp = sum(item.label == DEFER_LABEL and prediction == TEMPLATE_ID for item, prediction in selected)
        fn = sum(item.label == TEMPLATE_ID and prediction == DEFER_LABEL for item, prediction in selected)
        template_precision = ratio(tp, tp + fp)
        template_recall = ratio(tp, tp + fn)
        defer_precision = ratio(tn, tn + fn)
        defer_recall = ratio(tn, tn + fp)
        template_f1 = f1(template_precision, template_recall)
        defer_f1 = f1(defer_precision, defer_recall)
        result[language] = {
            "accuracy": ratio(tp + tn, len(selected)),
            "macro_f1": (template_f1 + defer_f1) / 2.0,
            "template_precision": template_precision,
            "template_recall": template_recall,
            "defer_precision": defer_precision,
            "defer_recall": defer_recall,
            "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        }
    return result


def evaluate_all(model_path: Path, examples: tuple[Example, ...]) -> dict[str, object]:
    raw = model_path.read_bytes()
    runner = QuantizedIntentCell(json.loads(raw), hashlib.sha256(raw).hexdigest())
    train = read_examples(DATA / "train.jsonl")
    dev = read_examples(DATA / "dev.jsonl")
    rules = RuleBaseline()
    nb = NaiveBayesBaseline()
    nb.fit(train)
    nb_selection = select_nb_threshold(nb, dev)
    nb_threshold = float(nb_selection["threshold"])
    predictions = {
        "rules": [rules.predict(item) for item in examples],
        "naive_bayes": [TEMPLATE_ID if nb.probability(item) >= nb_threshold else DEFER_LABEL for item in examples],
        "cell": [runner.infer(item.text, item.language).label for item in examples],
    }
    metrics = {name: evaluate_predictions(examples, values) for name, values in predictions.items()}
    gates = {}
    for language in LANGUAGES:
        best_baseline = max(
            float(metrics["rules"][language]["macro_f1"]),
            float(metrics["naive_bayes"][language]["macro_f1"]),
        )
        cell_metrics = metrics["cell"][language]
        gates[language] = {
            "best_baseline_macro_f1": best_baseline,
            "baseline_below_0_90": best_baseline < 0.90,
            "cell_improvement": float(cell_metrics["macro_f1"]) - best_baseline,
            "improvement_at_least_0_03": float(cell_metrics["macro_f1"]) - best_baseline >= 0.03,
            "defer_recall_at_least_0_95": float(cell_metrics["defer_recall"]) >= 0.95,
            "template_precision_at_least_0_90": float(cell_metrics["template_precision"]) >= 0.90,
        }
    return {
        "metrics": metrics,
        "gates": gates,
        "nb_development_selection": nb_selection,
        "model_threshold": runner.model["threshold"],
    }


def measure_resources(model_path: Path, examples: tuple[Example, ...]) -> dict[str, object]:
    raw = model_path.read_bytes()
    runner = QuantizedIntentCell(json.loads(raw), hashlib.sha256(raw).hexdigest())
    latencies = []
    tracemalloc.start()
    for _ in range(40):
        for item in examples:
            started = time.perf_counter()
            runner.infer(item.text, item.language)
            latencies.append((time.perf_counter() - started) * 1000)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ordered = sorted(latencies)
    p95 = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
    return {
        "artifact_bytes": len(raw),
        "input_limit_bytes": MAX_INPUT_BYTES,
        "latency_ms": {
            "p50": statistics.median(ordered),
            "p95": p95,
            "max": max(ordered),
            "samples": len(ordered),
        },
        "peak_traced_inference_bytes": peak,
        "host": {
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "gates": {
            "artifact_at_most_131072": len(raw) <= 131072,
            "p95_latency_at_most_5_ms": p95 <= 5.0,
            "peak_allocation_at_most_8_mib": peak <= 8 * 1024 * 1024,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen EXP-2026-003 harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("audit")
    train_parser = subparsers.add_parser("train-dev")
    train_parser.add_argument("--model", type=Path, required=True)
    train_parser.add_argument("--report", type=Path, required=True)
    heldout_parser = subparsers.add_parser("heldout")
    heldout_parser.add_argument("--model", type=Path, required=True)
    heldout_parser.add_argument("--expected-heldout-sha256", required=True)
    heldout_parser.add_argument("--source-commit", required=True)
    heldout_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    audit = audit_splits()
    if args.command == "audit":
        print(canonical_json(audit))
        return 0
    if args.command == "train-dev":
        train = read_examples(DATA / "train.jsonl")
        dev = read_examples(DATA / "dev.jsonl")
        model = build_model(train, dev)
        write_new_or_replace(args.model, canonical_json(model) + "\n")
        evaluation = evaluate_all(args.model, dev)
        report = {
            "schema": "engine.cell-development/v1",
            "experiment": "EXP-2026-003",
            "consumed_heldout": False,
            "audit": audit,
            "model_sha256": sha256_file(args.model),
            "evaluation": evaluation,
        }
        write_new_or_replace(args.report, canonical_json(report) + "\n")
        print(canonical_json(report))
        return 0

    heldout_path = DATA / "heldout.jsonl"
    actual = sha256_file(heldout_path)
    if actual != args.expected_heldout_sha256:
        raise SystemExit("held-out SHA-256 mismatch; refusing consumption")
    if args.output.exists():
        raise SystemExit("held-out output already exists; refusing a second consumption")
    if source_commit() != args.source_commit:
        raise SystemExit("working source commit differs from frozen source commit")
    examples = read_examples(heldout_path)
    evaluation = evaluate_all(args.model, examples)
    resources = measure_resources(args.model, examples)
    language_gates = [
        bool(value)
        for details in evaluation["gates"].values()
        for name, value in details.items()
        if name != "best_baseline_macro_f1" and name != "cell_improvement"
    ]
    result = {
        "schema": "engine.cell-heldout-result/v1",
        "experiment": "EXP-2026-003",
        "consumed_at": datetime.now(UTC).isoformat(),
        "source_commit": args.source_commit,
        "audit": audit,
        "heldout_sha256": actual,
        "model_sha256": sha256_file(args.model),
        "training_config_sha256": hashlib.sha256(canonical_json({
            "dimensions": DIMENSIONS,
            "hidden_size": HIDDEN_SIZE,
            "epochs": EPOCHS,
            "learning_rate": LEARNING_RATE,
            "l2": L2,
            "positive_class_weight": POSITIVE_CLASS_WEIGHT,
            "seed": SEED,
            "thresholds": THRESHOLDS,
        }).encode()).hexdigest(),
        "evaluation": evaluation,
        "resources": resources,
        "release_gate": {
            "passed": all(language_gates) and all(resources["gates"].values()),
            "language_gates_passed": all(language_gates),
            "resource_gates_passed": all(resources["gates"].values()),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical_json(result) + "\n", encoding="utf-8")
    print(canonical_json(result))
    return 0 if result["release_gate"]["passed"] else 2


def write_new_or_replace(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def sigmoid(value: float) -> float:
    if value >= 0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    direct = math.exp(value)
    return direct / (1.0 + direct)


if __name__ == "__main__":
    raise SystemExit(main())
