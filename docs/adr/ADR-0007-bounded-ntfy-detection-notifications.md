# ADR-0007 — Bounded outbound ntfy lifecycle notifications

- Status: accepted by explicit owner direction
- Owner: project owner
- Date: 2026-08-10

## Context

The owner wants meaningful Engine progress delivered to the ntfy topic
`pow-job-x` while Engine runs unattended, but explicitly does not want every
Homey detection forwarded. Raw household motion, lighting and sensor changes
are noisy and create an unnecessarily broad outbound privacy boundary.

The useful boundary is a durable Engine milestone: something was learned, a
goal or routine was added, or a model produced an actionable suggestion. These
facts are distinct from raw observations and must remain distinct from
authority and observed effects.

## Decision

1. ntfy is implemented by the separately installed `engine.ntfy` plugin. Core,
   the runtime composition root and `engine.homey` contain no ntfy endpoint or
   message semantics. The generic plugin contract exposes declared lifecycle
   observers, analogous to its declared providers and experience providers.
2. ntfy is disabled unless `ENGINE_NTFY_TOPIC` is explicitly configured.
3. The generic lifecycle contract emits a typed `LifecycleEventV1` only after
   the associated artifact or transition has been stored durably. The first
   notifier accepts only:

   - a `GoalSpec` being added;
   - a learning or routine candidate being created or promoted;
   - a `RoutineSpec` being added or activated;
   - a real `ProposedAction` produced by a model-backed brain.

4. Raw Homey motion, lighting, switch and sensor transitions are excluded, as
   are individual behavior signals, camera and alarm data, images, full
   snapshots, tokens, temperature, lux, power, inferred presence duration and
   opaque capabilities. Detecting one of these changes is not a notification
   milestone by itself.
5. Messages contain only the smallest deterministic projection needed to name
   the milestone and its durable artifact. They do not contain complete goals,
   snapshots, prompts, model context, secrets, or arbitrary capability values.
6. Remote endpoints require HTTPS. Topic names cannot contain paths or query
   syntax, and endpoint credentials are forbidden in the URL.
7. Notification delivery has no authority and is not an execution oracle.
   Delivery is best-effort. Failure is audited as
   `lifecycle_observer_failed` and cannot stop observation, policy,
   authorization or dispatch.

## Alternatives

- Export every Homey event or snapshot change: rejected because it is noisy,
  violates data minimization, and conflates observation with learning.
- Put ntfy directly in Engine core or the runtime composition root: rejected
  because outbound destinations and presentation semantics belong to plugins.
- Put ntfy in the Homey adapter: rejected because outbound presentation is a
  separate plugin concern, not Homey device semantics.
- Have an LLM summarize raw detections: rejected because deterministic bounded
  milestone text is sufficient and model/provider availability must not affect
  delivery. A genuine model `ProposedAction` may itself be announced, but the
  notifier does not call a model to generate its message.

## Consequences

The owner receives useful low-volume progress notifications without exporting
routine household telemetry. A lamp or motion sensor changing state produces no
ntfy message unless Engine later records one of the allowed durable milestones.
Delivery is best-effort and ntfy availability does not affect Engine
correctness. Anyone able to subscribe to the configured topic may see the
bounded messages, so the owner should treat the topic identifier as a shareable
access locator and rotate it when needed.

## Safety and scientific impact

The notifier cannot propose, authorize, dispatch or certify actions. A
notification about an LLM proposal is still only a report that an untrusted
proposal exists; it is not approval or proof of effect. Notifier output must not
be used as observation evidence. Persisted Engine artifacts and observations
remain the scientific source of truth.

## Migration and reversibility

Set `ENGINE_NTFY_TOPIC` to opt in. Unset it and restart Engine to remove the
outbound path. No stored Engine state requires migration.
