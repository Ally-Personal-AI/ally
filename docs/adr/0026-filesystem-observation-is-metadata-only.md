# ADR 0026: Filesystem observation is metadata-only and explicitly rooted

**Status:** Accepted

## Context

A local filesystem source is useful before authenticated email or calendar
integrations, but implicit document ingestion would violate Ally's local-data
and authority boundaries. A recursive watcher can also create unbounded work,
escape through symlinks, or produce duplicate storms after restart.

## Decision

The first filesystem adapter is a pull-based `EventSource` over one explicit
directory root.

It records only regular-file relative paths, sizes, modification times, and the
filesystem identity needed for best-effort rename matching. It never opens file
contents and never follows symlinks. Hidden entries are excluded by default.

The first poll establishes a baseline and emits no observations. Later polls
derive deterministic created, modified, moved, and deleted changes. A monotonic
sequence stored in the opaque cursor makes each external event ID unique across
time and stable across retry of the same checkpoint.

Both traversal and publication are bounded. Exceeding the traversal bound or
encountering a permission/scan failure aborts the poll without advancing the
checkpoint. When changes exceed the publication limit, the returned cursor
applies only the emitted prefix so remaining changes appear on later polls.

The checkpoint contains a compact relative-path snapshot and no absolute root
or file content. Device/inode values never enter event payloads. On a restored
machine, unchanged paths with unchanged public metadata do not emit events even
if filesystem identities differ.

## Consequences

Users explicitly choose every observed root and may choose whether hidden files
or user-facing event importance are appropriate. The adapter can miss a content
change that preserves both size and modification time; detecting that would
require a separate, explicitly authorized content-reading capability.

Move detection is best effort. Ambiguous hard links or inode reuse safely
degrade to create/delete behavior rather than reading content to disambiguate.

Continuous execution remains the responsibility of the managed-service layer,
not the source adapter.
