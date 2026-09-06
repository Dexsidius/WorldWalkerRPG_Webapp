# Worldwalker contributor instructions

## Required update destinations

Richard requested on September 6, 2026 that future authorized game updates be
published to both of these destinations:

- `richardmadden1030-dot/worldwalker-rpg` — branch `master`.
- `Dexsidius/WorldWalkerRPG_Webapp` — branch `web_prod`.

For each requested implementation update:

1. Read the current tips of both branches and compare their relevant files.
2. Preserve destination-specific deployment configuration and unrelated work.
   When histories diverge, port the intended changes rather than replacing the
   destination tree or force-pushing it.
3. Run relevant available checks and publish the update to both branches using
   non-force writes. A successful account permission read is not proof that the
   active integration can write to the second repository.
4. Verify each resulting branch tip and report the actual commit or failure
   separately. Never describe a failed secondary push as synchronized.
5. If GitHub denies access, stop writes to that destination and request the
   repository owner's approval for the connected integration. Do not bypass
   access controls or search for credentials.

The `Dexsidius` repository is public. Publish only approved project changes;
never include local credentials, API keys, player saves or personal data.
These instructions are a publishing workflow, not an unattended sync service.

## Windows distribution

When an executable is requested, build and verify a Windows package containing
that update, or provide a verified existing download with its limitations.
Do not present GitHub's source-code ZIP or an older release as the updated EXE.
Keep the full portable folder together, including `_internal`; preserve player
saves and settings and do not replace the stable release without authorization.
