# Security Policy

Ally is pre-release software and should not yet be trusted with consequential automation or irreplaceable sensitive data.

Please do not disclose suspected vulnerabilities in a public issue. Until a dedicated security reporting channel is published, contact the repository maintainers privately through GitHub.

## Security priorities

- prevent leakage of personal data
- prevent unauthorized tool execution
- protect credentials and secrets
- preserve permission boundaries
- provide auditable behavior
- keep local-only operation possible

## Automated scanning

The independent `Security` workflow runs for pull requests, pushes to `main`,
manual dispatches, and every Monday. It has read-only repository contents
permission and checks two supply-chain boundaries:

- `pip-audit` checks the exact runtime dependency graph exported from the
  committed `uv.lock` against the Python Packaging Advisory Database.
- `zizmor` statically checks GitHub workflow and Dependabot definitions in
  offline mode. All third-party Actions must use immutable commit SHAs.

The security job installs its scanners from the committed lockfile and does not
upload source, prompts, personal state, or generated user data to a third-party
analysis service. Dependency advisory lookups disclose package names and
versions to the Python Package Index advisory API; workflow analysis is local
to the GitHub-hosted runner.

## Finding triage

A new dependency vulnerability or regular-persona workflow finding blocks the
security check. The pull-request author owns initial remediation; a maintainer
reviews whether to upgrade, remove, or replace the dependency or workflow
construct. Never suppress a finding only to make CI green.

If a report is demonstrably inapplicable, document the threat-model reasoning,
advisory identifier, owner, and review date in the pull request before adding a
narrow exception. Expired or undocumented exceptions must be removed.

Scanner availability does not gate the independent Ubuntu/macOS product CI.
For an upstream outage, leave the security check unmerged or retry it after the
service recovers; do not weaken product tests or grant broader workflow
permissions.
