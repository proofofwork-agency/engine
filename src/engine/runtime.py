from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
import time

from .heart import Heart
from .store import EngineStore


@dataclass(frozen=True)
class RuntimePass:
    goals_seen: int
    active_remaining: bool
    failures: int


class LiveEngine:
    """Always-on event/poll driver for Engine's deliberative Heart.

    Target events are wake-up hints only. Heart always observes the target again
    before it reasons or acts. Stable maintained goals therefore cost observation,
    not repeated model calls. Hard-realtime device control remains outside Engine.
    """

    retry_memory_key = "live_runtime_retry"

    def __init__(
        self,
        heart: Heart,
        poll_interval: float = 1.0,
        failure_backoff_initial: float = 1.0,
        failure_backoff_max: float = 60.0,
        failure_threshold: int = 3,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        if failure_backoff_initial <= 0 or failure_backoff_max <= 0:
            raise ValueError("failure backoff values must be positive")
        if failure_backoff_initial > failure_backoff_max:
            raise ValueError("initial failure backoff cannot exceed its maximum")
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        self.heart = heart
        self.poll_interval = poll_interval
        self.failure_backoff_initial = failure_backoff_initial
        self.failure_backoff_max = failure_backoff_max
        self.failure_threshold = failure_threshold
        self._wake = Event()
        self._stop = Event()
        self._running = False
        self._unsubscribe: list[Callable[[], None]] = []
        self._runtime_heart: Heart | None = None
        self._owns_runtime_store = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def wake_pending(self) -> bool:
        return self._wake.is_set()

    def wake(self, *_event: object) -> None:
        """Wake the Heart; the event payload is deliberately not trusted as state."""
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def run_once(self) -> RuntimePass:
        """Give every live goal one fair Heart step or monitoring observation."""
        heart = self._runner
        failures = 0
        goals = heart.store.live_goals()
        for goal in goals:
            if self._stop.is_set():
                break
            retry = heart.store.load_memory(goal.id).get(self.retry_memory_key)
            if isinstance(retry, dict):
                retry_at = float(retry.get("retry_at_epoch", 0.0))
                if retry_at > time.time():
                    continue
                if goal.status == "degraded":
                    goal = heart.store.set_goal_status(goal.id, "active")
            events_before = heart.store.all_events(goal.id)
            last_event_id = events_before[-1].id if events_before else 0
            try:
                result = heart.run(goal.id, step_limit=1)
            except Exception as error:
                failures += 1
                self._record_goal_failure(goal.id, error, last_event_id)
            else:
                if isinstance(retry, dict) and self._retry_resolved(
                    goal.id, retry, result, last_event_id
                ):
                    heart.store.delete_memory(goal.id, self.retry_memory_key)
                    current = heart.store.get_goal(goal.id)
                    heart.store.append_event(
                        goal.id,
                        current.cycle,
                        "runtime_goal_recovered",
                        "live-heart",
                        {"attempts": int(retry.get("attempts", 0))},
                    )
        now = time.time()
        active_remaining = any(
            goal.status == "active" and self._retry_due(goal.id, now)
            for goal in heart.store.live_goals()
        )
        return RuntimePass(
            goals_seen=len(goals),
            active_remaining=active_remaining,
            failures=failures,
        )

    def run_forever(self) -> None:
        """Stay alive until stopped, sleeping when no cognition is runnable."""
        if self._running:
            raise RuntimeError("LiveEngine is already running")
        self._running = True
        self._stop.clear()
        self._wake.clear()
        started_recorded = False
        try:
            self._runtime_heart = self._heart_for_current_thread()
            self._attach_event_sources()
            self._runner.store.append_system_event(
                "live_heart_started",
                {
                    "poll_interval": self.poll_interval,
                    "failure_backoff_initial": self.failure_backoff_initial,
                    "failure_backoff_max": self.failure_backoff_max,
                    "failure_threshold": self.failure_threshold,
                },
            )
            started_recorded = True
            while not self._stop.is_set():
                result = self.run_once()
                if self._stop.is_set():
                    break
                if result.active_remaining and result.failures == 0:
                    continue
                self._wake.wait(self.poll_interval)
                self._wake.clear()
        finally:
            try:
                self._detach_event_sources()
                if started_recorded:
                    self._runner.store.append_system_event(
                        "live_heart_stopped", {}
                    )
            finally:
                if self._owns_runtime_store and self._runtime_heart is not None:
                    self._runtime_heart.store.close()
                self._runtime_heart = None
                self._owns_runtime_store = False
                self._running = False

    @property
    def _runner(self) -> Heart:
        return self._runtime_heart or self.heart

    def _heart_for_current_thread(self) -> Heart:
        if self.heart.store.owned_by_current_thread:
            self._owns_runtime_store = False
            return self.heart
        store = EngineStore(self.heart.store.path)
        try:
            heart = Heart(
                store,
                self.heart.executive,
                self.heart.catalog,
                experience_window=self.heart.experience_window,
                capability_limit=self.heart.capability_limit,
                require_specialist_first=self.heart.require_specialist_first,
            )
        except Exception:
            store.close()
            raise
        self._owns_runtime_store = True
        return heart

    def _record_goal_failure(
        self, goal_id: str, error: Exception, last_event_id: int
    ) -> None:
        heart = self._runner
        current = heart.store.get_goal(goal_id)
        previous = heart.store.load_memory(goal_id).get(self.retry_memory_key)
        previous_attempts = (
            int(previous.get("attempts", 0)) if isinstance(previous, dict) else 0
        )
        events = heart.store.all_events(goal_id)
        latest = events[-1] if events else None
        failed_brain_id: str | None = None
        if (
            latest is not None
            and latest.id > last_event_id
            and latest.kind == "brain_result"
            and latest.payload.get("status") == "failed"
        ):
            failed_brain_id = str(latest.payload.get("brain_id", latest.source))
        attempts = previous_attempts + 1
        delay = min(
            self.failure_backoff_initial * (2 ** (attempts - 1)),
            self.failure_backoff_max,
        )
        retry_at = time.time() + delay
        heart.store.set_memory(
            goal_id,
            self.retry_memory_key,
            {
                "attempts": attempts,
                "delay_seconds": delay,
                "retry_at_epoch": retry_at,
                "error": f"{type(error).__name__}: {error}",
                "failed_stage": "brain" if failed_brain_id else "heart",
                "failed_brain_id": failed_brain_id,
            },
        )
        heart.store.append_event(
            goal_id,
            current.cycle,
            "runtime_goal_error",
            "live-heart",
            {
                "error": f"{type(error).__name__}: {error}",
                "attempts": attempts,
                "retry_in_seconds": delay,
            },
        )
        if attempts >= self.failure_threshold:
            heart.store.append_event(
                goal_id,
                current.cycle,
                "runtime_circuit_open",
                "live-heart",
                {"attempts": attempts, "retry_in_seconds": delay},
            )
            heart.store.set_goal_status(goal_id, "degraded")

    def _retry_resolved(
        self,
        goal_id: str,
        retry: dict[str, object],
        result: object,
        last_event_id: int,
    ) -> bool:
        failed_stage = str(retry.get("failed_stage", "heart"))
        if failed_stage != "brain":
            return True
        goal = getattr(result, "goal", None)
        if goal is not None and goal.status in {
            "completed",
            "monitoring",
            "abandoned",
            "budget_exhausted",
            "degraded",
        }:
            return True
        failed_brain_id = retry.get("failed_brain_id")
        return any(
            event.kind == "brain_result"
            and event.id > last_event_id
            and event.payload.get("status") == "succeeded"
            and event.payload.get("brain_id") == failed_brain_id
            for event in self._runner.store.all_events(goal_id)
        )

    def _retry_due(self, goal_id: str, now: float) -> bool:
        retry = self._runner.store.load_memory(goal_id).get(self.retry_memory_key)
        if not isinstance(retry, dict):
            return True
        return float(retry.get("retry_at_epoch", 0.0)) <= now

    def _attach_event_sources(self) -> None:
        self._detach_event_sources()
        for target in self._runner.catalog.targets.values():
            subscribe = getattr(target, "subscribe", None)
            if not callable(subscribe):
                continue
            try:
                unsubscribe = subscribe(self.wake)
            except Exception as error:
                self._runner.store.append_system_event(
                    "target_subscription_failed",
                    {
                        "target_id": target.manifest.id,
                        "error": f"{type(error).__name__}: {error}",
                        "fallback": "polling",
                    },
                )
                continue
            if callable(unsubscribe):
                self._unsubscribe.append(unsubscribe)

    def _detach_event_sources(self) -> None:
        while self._unsubscribe:
            unsubscribe = self._unsubscribe.pop()
            try:
                unsubscribe()
            except Exception:
                # Shutdown remains best-effort; target state is observed on next start.
                pass
