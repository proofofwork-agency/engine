from __future__ import annotations

import json
import hashlib
from typing import Any
from urllib import error, request

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


class LlamaCppDecisionModel:
    """Small provider bridge for a schema-constrained general brain.

    The default endpoint is loopback-only llama.cpp. The class deliberately owns
    no goal, world state, transcript, or tools: every call receives a fresh Engine
    context and returns one untrusted structured decision.
    """

    base_decision_schema = {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": [
                    "consult_brain",
                    "use_tool",
                    "wait",
                    "complete",
                    "abandon",
                ],
            },
            "name": {"type": "string"},
            "arguments": {"type": "object"},
            "rationale": {"type": "string", "maxLength": 200},
            "based_on": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["kind", "name", "arguments", "rationale", "based_on"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:18080/v1",
        model: str = "local-model",
        api_key: str = "no-key",
        timeout_seconds: float = 120.0,
        temperature: float = 0.0,
        max_input_bytes: int = 64_000,
        keep_session_history: bool = False,
        history_turn_limit: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_input_bytes = max_input_bytes
        self.keep_session_history = keep_session_history
        self.history_turn_limit = history_turn_limit
        self._history: list[dict[str, str]] = []
        self.last_usage: dict[str, Any] = {}

    def decide(self, context: dict[str, object]) -> dict[str, object]:
        self.last_usage = {}
        projection = self._context_projection(context)
        serialized_projection = json.dumps(
            projection, sort_keys=True, separators=(",", ":")
        )
        user_message = {"role": "user", "content": serialized_projection}
        messages = [
            {"role": "system", "content": self._system_prompt()},
            *self._history,
            user_message,
        ]
        projection_bytes = json.dumps(
            messages, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(projection_bytes) > self.max_input_bytes:
            raise RuntimeError(
                f"provider projection exceeds byte budget: "
                f"{len(projection_bytes)} > {self.max_input_bytes}"
            )
        decision_schema = self._decision_schema(projection)
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": 640,
            "messages": messages,
            "json_schema": decision_schema,
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_effort": "none",
        }
        encoded = json.dumps(body).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}/chat/completions",
            data=encoded,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(
                http_request, timeout=self.timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"decision provider rejected request ({exc.code}): {details}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"decision provider unavailable: {exc}") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("decision provider returned a non-object response")
        self.last_usage = {
            "provider": "openai-compatible",
            "model": payload.get("model", self.model),
            "usage": payload.get("usage", {}),
            "timings": payload.get("timings", {}),
            "provider_projection_sha256": hashlib.sha256(
                projection_bytes
            ).hexdigest(),
            "input_bytes": len(projection_bytes),
        }
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("decision provider returned no choices")
        first_choice = choices[0]
        message = first_choice.get("message") if isinstance(first_choice, dict) else None
        if not isinstance(message, dict):
            raise RuntimeError("decision provider returned no message object")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("decision provider returned no JSON content")
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            finish_reason = payload.get("choices", [{}])[0].get("finish_reason")
            raise RuntimeError(
                "decision provider returned invalid JSON "
                f"(finish_reason={finish_reason}): {content!r}"
            ) from exc
        if not isinstance(value, dict):
            raise RuntimeError("decision provider returned a non-object")
        try:
            Draft202012Validator(decision_schema).validate(value)
        except ValidationError as exc:
            raise RuntimeError(
                f"decision provider violated schema: {exc.message}: {value!r}"
            ) from exc
        if self.keep_session_history:
            self._history.extend(
                [user_message, {"role": "assistant", "content": content}]
            )
            if self.history_turn_limit is not None:
                if self.history_turn_limit <= 0:
                    self._history.clear()
                else:
                    self._history = self._history[-2 * self.history_turn_limit :]
        return value

    def reset_session(self) -> None:
        self._history.clear()

    @staticmethod
    def _context_projection(context: dict[str, object]) -> dict[str, object]:
        """Bounded provider view; Engine retains the full durable event history."""
        recent = context.get("recent_experience", [])
        relevant_kinds = {
            "tool_result",
            "brain_outcome",
            "completion_rejected",
            "stale_advice_rejected",
            "budget_exhausted",
        }
        relevant = [
            event
            for event in recent
            if isinstance(event, dict) and event.get("kind") in relevant_kinds
        ][-8:]
        specialists = []
        for specialist in context.get("specialists", []):
            if isinstance(specialist, dict):
                specialists.append(
                    {
                        "id": specialist.get("id"),
                        "description": specialist.get("description"),
                        "supported_capabilities": specialist.get(
                            "supported_capabilities", []
                        ),
                        "version": specialist.get("version"),
                    }
                )
        pending = context.get("pending_advice", [])
        return {
            "goal": context.get("goal"),
            "snapshot": context.get("snapshot"),
            "capabilities": context.get("capabilities"),
            "specialists": specialists,
            "cognitive_phase": context.get("cognitive_phase"),
            "pending_advice": pending,
            "specialist_performance": context.get("specialist_performance"),
            "recent_outcomes": relevant,
            "specialist_query": context.get("specialist_query"),
        }

    @classmethod
    def _decision_schema(cls, projection: dict[str, object]) -> dict[str, object]:
        specialists = projection.get("specialists") or []
        advice = projection.get("pending_advice") or []
        capabilities = projection.get("capabilities") or []
        if advice:
            kinds = ["use_tool", "wait", "abandon"]
        elif specialists:
            kinds = ["consult_brain", "wait", "abandon"]
        else:
            kinds = ["use_tool", "wait", "complete", "abandon"]
        names = [""]
        specialist_ids = [
            str(item.get("id"))
            for item in specialists
            if isinstance(item, dict) and item.get("id")
        ]
        capability_ids = [
            str(item.get("id"))
            for item in capabilities
            if isinstance(item, dict) and item.get("id")
        ]
        names.extend(specialist_ids)
        names.extend(capability_ids)
        advice_ids = [
            str(item.get("brain_request_id"))
            for item in advice
            if isinstance(item, dict) and item.get("brain_request_id")
        ]
        schema = json.loads(json.dumps(cls.base_decision_schema))
        schema["properties"]["kind"]["enum"] = kinds
        schema["properties"]["name"]["enum"] = sorted(set(names))
        if advice_ids:
            schema["properties"]["based_on"]["items"]["enum"] = advice_ids
        else:
            schema["properties"]["based_on"]["maxItems"] = 0
        # Keep the generation grammar flat. llama.cpp's JSON-schema grammar
        # support produced incomplete objects for the logically stronger oneOf
        # form in a consumed live canary. Heart independently enforces the
        # conditional kind/name/based_on semantics after generation.
        return schema

    @staticmethod
    def _system_prompt() -> str:
        return """You are Engine's general executive brain. /no_think
Return exactly one JSON decision matching the supplied schema. You reason and
choose; Heart owns goals, memory, invocation, observation, and truth.

Decision priority (follow exactly):
- If pending_advice contains fresh advice with a
  suggested_action, emit use_tool for that exact suggested_action and put only
  its brain_request_id in based_on.
- Otherwise, if a specialist has overlap between supported_capabilities and the
  visible capabilities, emit consult_brain with that specialist's exact id.
- Only when no specialist matches may you emit use_tool directly.

Rules:
- Use only specialist ids and capability ids present in the context.
- If there is fresh specialist advice in pending_advice,
  decide whether it is useful. To use it, emit use_tool with the exact qualified
  capability id, its arguments, and the brain_request_id in based_on.
- If specialists exist and no useful fresh advice exists, normally consult the
  best matching specialist before acting. For this evaluation that is mandatory.
- If no specialist matches, choose a world capability yourself from the visible
  goal, snapshot, and JSON Schemas.
- Never claim complete unless the observed snapshot already satisfies success_spec.
- A failed prior action is evidence: adapt instead of blindly repeating it.
- based_on is [] for consult_brain/direct use_tool and contains only specialist
  brain_request_ids when consuming advice. Never put a goal id there.
- name is the selected qualified brain/capability id, or an empty string for
  terminal/wait.
"""


# Compatibility name for callers written before the llama.cpp dialect was made
# explicit. It remains a provider seam, not a claim of universal API compatibility.
OpenAICompatibleDecisionModel = LlamaCppDecisionModel
