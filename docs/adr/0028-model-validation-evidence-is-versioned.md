# ADR 0028: Model validation evidence is versioned and comparison is neutral

**Status:** Accepted

## Context

Ally must choose an initial local runtime and model from measurements on the
target machine. The first validation report recorded evaluation outcomes and a
machine profile, but not the runtime version, model format, context setting,
evaluation-file identity, or runtime-native performance observations. Manual
notes would make later comparisons incomplete and difficult to reproduce.

A single aggregate score would also encode an arbitrary product decision. Raw
generation speed cannot safely substitute for instruction reliability, memory
headroom, usable context, stability, or proposal quality.

## Decision

Local-model validation produces a strict, schema-versioned evidence artifact.
It records a non-sensitive runtime profile, content hashes of the frozen case
files, the machine profile, complete evaluation results, and optional
runtime-native observations. Reports are bounded when loaded and never
overwrite existing evidence.

Runtime parameters are explicit name/value records rather than a raw command
line. Common credential-bearing names and multiline values are rejected. The
operator remains responsible for supplying only public, non-personal metadata.

Comparison verifies whether reports share hardware and evaluation fingerprints,
surfaces mismatches, and presents the constituent evidence. It does not compute
a composite score, rank candidates, or select Ally's default runtime or model.

## Consequences

The dedicated-machine session can produce comparable artifacts instead of
unstructured notes, and future hardware or model changes can reuse the same
contract. Report-schema changes require an explicit version change and loader
policy rather than silently changing historical meaning.

Some performance observations remain manual because OpenAI-compatible APIs do
not standardize all runtime telemetry. Missing data stays explicitly absent;
Ally does not estimate it. The final runtime/model decision remains a human
judgment informed by repeated functional and operational evidence.
