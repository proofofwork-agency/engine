# Engine Homey / HomeOps

HomeOps is an installable world plugin on Engine. It represents one Homey Pro as
one whole-house target, without creating a Homey app, Homey Flows, room code or
brand code. The original v1 application remains available; the v2 entrypoint
uses Engine's generic multi-target world and action lifecycle.

The first release is deliberately local-first and deterministic:

- HTTP reads are authoritative observations; Socket.IO messages only wake Heart.
- Polling repairs missed or duplicate events.
- Mutations are denied unless `ENGINE_HOMEY_MODE=act` and
  `ENGINE_HOMEY_ARMED=1` are both set.
- Only configured device aliases and capability IDs can be mutated.
- A mutation also requires a recent full Homey read and Homey must explicitly
  report the target device as available and the capability as settable.
- HTTP acknowledgement is not success: the adapter reads Homey again and checks
  the commanded capability. The house oracle independently checks the charter's
  sensor outcome (for example lux and watts).
- HomeOps keeps aliases, monotone snapshot revisions, charter versions and
  preference evidence in its own SQLite database. Engine receipts remain in a
  separate Engine database.

## Install and configure

```shell
pip install -e plugins/engine-homey
cp plugins/engine-homey/examples/homey.toml ./homey.toml
export ENGINE_HOMEY_CONFIG="$PWD/homey.toml"
export ENGINE_HOMEY_TOKEN='<personal-access-token>'
engine-homey discover
```

Alternatively, keep OAuth entirely inside the official Homey CLI:

```shell
homey login
homey select
engine-homey connect --from-cli
export ENGINE_HOMEY_AUTH=cli
engine-homey discover
```

CLI-auth mode exports no token to Engine and uses polling. Direct HTTP/PAT mode
remains available when Socket.IO wake hints are wanted.

Use a Personal Access Token with `homey.device.readonly` and
`homey.zone.readonly` for discovery/observe mode. Add `homey.device.control`
only for act mode. The token is read only from the environment and is never
persisted or included in errors.

Compile and run the permanent maintained-house goal:

```shell
engine-homey compile-charter charter.txt
engine-homey run
```

For a bounded dry check, use `engine-homey run --once`. For real mutations,
change the config to `mode = "act"` (or set `ENGINE_HOMEY_MODE=act`) and arm the
process explicitly:

```shell
export ENGINE_HOMEY_ARMED=1
engine-homey run
```

Direct corrections create versioned charter patches:

```shell
engine-homey correct 'Na 23:00 is dit te fel' --zone garden
```

An externally observed change to an allowlisted control capability is recorded
as `INFERRED`, unattributed control-change evidence and never patches the charter
automatically. It might come from a person, a Homey Flow, or another integration;
the plugin does not claim to know which. `engine-homey record-override` records an
explicitly reported manual override when its provenance is known.

For v2, `mode=act` plus process arming is the transport killswitch; a persistent
`StandingMandateV1` and exact request-bound `AuthorizationV1` are additionally
required by Heart before dispatch.

## Configuration model

All devices remain observable. A device is controllable only when it has an
explicit binding with a non-empty `control` allowlist. Semantic action fields can
be mapped to vendor/device capability IDs with `capability_map`, so the adapter
contains no room-, brand- or situation-specific branches.

`plugin_database` and `engine_database` must resolve to different files. The
default example puts both beside the config under distinct filenames.

## Current evidence boundary

The automated suite uses a deterministic fake Homey server and proves protocol,
reconstruction, event/poll recovery, a composed Homey+context world, three-zone
GoalSpec reuse, eight camera detection entities, exact lifecycle records,
sensor-based completion, ACK-without-effect failure and zero stable model calls.
It is simulation evidence, not a claim that v2 live actuation has run. The
five-run physical lux/watt gate remains open.

Official protocol references:

- https://athombv.github.io/node-homey-api/HomeyAPI.html
- https://athombv.github.io/node-homey-api/HomeyAPIV3Local.ManagerDevices.html
- https://api.developer.homey.app/http-and-socket.io/socket.io-specification

The staged live procedure, five-run measurement sheet requirements and rollback
path are in [`DEPLOYMENT.md`](DEPLOYMENT.md).
