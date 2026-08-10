# reference-world

A deliberately non-house `engine.plugin/v2` reference: a warehouse grid with an
incoming bin, reserve bin, sensors and a durable crate-transfer task.

It exists as an architecture acceptance test. The same `WorldHeartV2` that runs
Homey must maintain the reserve target here without changes to Engine core.
Factory creation is inert, state and task idempotency survive restart, and an
effect oracle compares pre-state, receipt and fresh post-state.

