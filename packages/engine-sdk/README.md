# engine-sdk

Dependency-light public contracts and bootstrap tooling for
`engine.plugin/v3`, with v2 compatibility for plugins without autonomy.

```shell
engine-plugin init my-world --template world
cd my-world
engine-plugin validate
engine-plugin inspect
engine-plugin test
```

Templates are `world`, `specialist` and `full`. The world/full template is a
non-house warehouse simulator with a task action and effect oracle. Its generated
conformance suite runs without editing Engine core.

Every v3 plugin supplies a static `engine-plugin.toml` with explicit
`[autonomy]` declarations and an `engine.plugins`
entrypoint. Import and factory invocation are inert. Dynamic instances may only
use predeclared capability families; an undeclared family is projected as
opaque/read-only until its typed manifest is enrolled.

V3 plugins may additionally expose proposal-only `AutonomyStrategy` values and
typed `GoalTemplateSpecV1`/inert compiler pairs. Heart retains mode, enrollment,
scheduling, cognition routing, policy, authorization, dispatch, recovery, and
effect verification.
