# Skill System

Tools expose atomic capabilities. Skills compose tools, policies, prompts,
knowledge, and workflows into reusable behavior.

A skill may eventually contain:

- a manifest
- declared permissions
- tool dependencies
- configuration schema
- workflow logic
- tests/evaluations
- documentation

Skills must be installable without modifying Ally Core.

Generated skills will eventually be built and tested in a sandbox before a user
is asked to approve their permissions and installation.
