# ADR 0037: Model and runtime artifacts are fingerprinted in validation evidence

**Status:** Accepted

## Context

Runtime name/version and model source identifiers are useful but do not prove
which exact files were tested. Model repositories can change, runtime binaries
can be rebuilt, caches can contain multiple revisions, and filenames alone do
not establish content identity.

Ally's first-machine evidence should be reproducible without persisting private
filesystem paths.

## Decision

Local-model validation may record repeated model and runtime artifact
fingerprints.

Each fingerprint contains only:

- the leaf filename;
- byte size; and
- SHA-256.

Hashing streams file contents in bounded memory. Ally compares file identity,
size, and modification metadata before/after hashing and fails closed if an
artifact changes or is replaced during fingerprinting.

Model artifacts may represent one weight file or multiple shards. When model
artifacts are supplied, their total byte size becomes the authoritative
`model_size_bytes`; conflicting size metadata is rejected.

Runtime artifacts are optional because some runtimes are installed as managed
packages rather than one executable file. When a stable binary, wheel, package,
or other runtime artifact is available, operators should fingerprint it.

Validation evidence stores no absolute/local filesystem path.

## Consequences

Repeated validation can establish whether the same content was tested even when
files move. Runtime-privacy source verification naturally includes these
fingerprints because it compares the complete runtime profile.

Fingerprints establish content identity, not publisher trust or authenticity.
Future signed model/runtime provenance may build on this evidence.
