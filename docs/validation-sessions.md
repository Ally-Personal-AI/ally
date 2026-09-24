# Resumable Validation Sessions

Validation sessions coordinate Ally's candidate qualification lifecycle without
creating another source of truth.

## Initialize

Start a session before generating candidate evidence:

```bash
ally validation-session init candidate-a \
  --directory validation/candidate-a
```

The session creates only `session.json`. By default it expects these files in
the same directory:

- `capability.json`
- `workflows.json`
- `privacy.json`
- `profile.json`

If evidence already exists under different leaf filenames, initialize with
`--capability-artifact`, `--workflow-artifact`,
`--privacy-artifact`, and `--profile-artifact`.

## Inspect the plan

```bash
ally validation-session show validation/candidate-a/session.json
```

The manifest is immutable. It contains no pass/fail flags, prompts, model
outputs, credentials, personal data, or absolute evidence paths.

## Refresh live state

```bash
ally validation-session refresh validation/candidate-a/session.json
```

Refresh recomputes:

1. machine readiness;
2. capability/behavior evidence;
3. source-bound functional workflow evidence;
4. source-bound runtime privacy evidence; and
5. the validated runtime profile.

The output also gives one deterministic `next_step`.

## Verify completion

```bash
ally validation-session verify validation/candidate-a/session.json
```

Verification exits successfully only when live readiness passes and the
capability, workflow, privacy, and validated-profile stages all currently
verify.

## Tamper and restart behavior

No completion state is cached. If an artifact is replaced, corrupted, or no
longer matches its source capability report, the next refresh reports the
affected stage as `inconsistent`.

Because state is derived rather than incrementally trusted, a session can be
resumed after a process exit or machine reboot by loading the same manifest and
evidence directory.

## Authority boundary

A validation session coordinates existing evidence contracts. It cannot:

- mark privacy passed;
- bypass capability or workflow failures;
- create production eligibility from missing evidence;
- override profile verification; or
- select a runtime automatically.

That separation is intentional.
