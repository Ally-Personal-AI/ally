# Local filesystem event source

Ally can observe regular-file metadata below one explicitly selected local
directory. It does not read file contents, follow symbolic links, or scan any
path outside that root.

The first poll establishes a baseline without emitting an event storm:

```bash
uv run ally sources poll-filesystem \
  --source-id files.documents \
  "$HOME/Documents"
```

Run the same command again to publish bounded `filesystem.created`,
`filesystem.modified`, `filesystem.moved`, and `filesystem.deleted` events.
Use the same source ID for the same logical root so Ally can resume its portable
checkpoint.

## Privacy and safety behavior

- Only relative path, file size, and nanosecond modification time enter event
  payloads. File contents are never opened or hashed.
- Device and inode values are held only inside the opaque local checkpoint for
  best-effort rename detection; they are not copied into event payloads.
- Symbolic links and non-regular files are ignored. A symbolic-link root is
  rejected, preventing an allowlist from silently redirecting elsewhere.
- Hidden files and directories are ignored unless `--include-hidden` is set.
- Any scan or permission failure aborts the poll. The prior checkpoint remains
  unchanged, so the next successful poll can retry without losing changes.
- `--max-entries` bounds all inspected directory entries, while `--limit`
  bounds observations published per poll. Excess changes remain represented by
  the cursor and are emitted on later polls.

File moves are detected by filesystem identity when the removed and added
identities are unambiguous. Otherwise they safely appear as separate delete and
create events. Content-only changes that preserve both file size and
modification time cannot be detected without reading content and are therefore
outside this adapter's privacy boundary.

## Attention behavior

The default event importance is `routine`. To make changes available to a
user-facing attention sink, opt into a higher importance explicitly:

```bash
uv run ally sources poll-filesystem \
  --source-id files.documents \
  "$HOME/Documents" \
  --importance important
```

The source uses the same event, checkpoint, dedupe, and proactive attention
runtime as every other Ally source. Continuous polling is intentionally left to
the future managed-service wrapper; this command performs one bounded cycle.
