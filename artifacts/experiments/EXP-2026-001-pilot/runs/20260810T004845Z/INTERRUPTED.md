# ABORTED-INSTRUMENT

The run was interrupted after the raw traces showed a live provider-schema
compatibility failure. The new Draft 2020-12 `oneOf` decision schema passed the
Python validator but llama.cpp's JSON-schema grammar repeatedly emitted
incomplete objects (for example missing `kind`). C0 and C1 recorded zero accepted
decisions on completed arms. No condition result from this directory is valid
pilot evidence.

Remediation: restore the previously proven flat phase schema for generation,
retain Heart's independent semantic validation, and require a live one-call
provider canary before rerunning all conditions.
