# engine.ntfy

`engine.ntfy` is an opt-in lifecycle-observer plugin. It sends compact,
deterministic notifications only for these durable Engine milestones:

- a `GoalSpec` is added;
- a learning or routine candidate is created or promoted;
- a `RoutineSpec` is added or activated;
- a model-backed brain produces a real `ProposedAction`.

It does **not** send raw Homey motion, light, switch, sensor, lux, power,
snapshot, or behavior-signal events. A detected state transition is therefore
not itself a notification. Engine must first persist one of the bounded
lifecycle milestones above.

```sh
export ENGINE_NTFY_TOPIC='pow-job-x'
export ENGINE_NTFY_TITLE='engine'
engine run
```

Optional variables:

- `ENGINE_NTFY_BASE_URL` defaults to `https://ntfy.sh`;
- `ENGINE_NTFY_TIMEOUT_SECONDS` defaults to `5`.

Remote endpoints require HTTPS. Unset `ENGINE_NTFY_TOPIC` and restart Engine to
disable all outbound notifications.

Delivery is best-effort and non-authoritative. The plugin cannot add world
facts, propose or authorize actions, dispatch mutations, or certify an effect.
A delivery failure is isolated and audited; it cannot stop Engine observation,
policy, authorization, execution, or effect verification.
