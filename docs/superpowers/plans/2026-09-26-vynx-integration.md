# VYNX domain and operational integration

Goal: combine the reviewed Android licensing and ringbuf changes, use vynx.com.tr for product navigation, and add tested operator audit/backup tools without publishing or changing repository visibility.

Architecture: preserve existing remote-desktop and managed-inventory protocol boundaries. VYNX product links are generated from a public brand profile. No account API fallback is guessed. The managed API deployment example uses desk-api.vynx.com.tr but remains opt-in until provisioned. Operator events are recorded in the same SQLite transaction as each mutation; backups use SQLite's online backup API.

Constraints: preserve AGPL notices, internal application IDs, source rights and explicit self-hosted configuration. Never embed production secrets. No relay license enforcement, payment activation, app attestation or physical-device success is claimed. Do not modify master, DNS, live website, or repository visibility.

- [x] Reconstruct PR #2 and #3 from exact tree hashes; run combined existing Python suites.
- [x] Add failing branding, operator-audit and backup tests; retain failures as evidence.
- [x] Implement canonical product links, empty unconfigured account fallback, brand-domain boundary tests, VYNX deployment profile and source/private-development handoff.
- [x] Implement transactional operator journal and restrictive online backup CLI; test failures, replay of operator commands, corrupted databases, symlinks and no overwrite.
- [ ] Verify the combined candidate locally and on clean CI; publish only an isolated branch/PR and report all remaining blockers.

Review focus: mixed product/API identities; accidental secret export; audit failures must roll back mutations; WAL backups must include committed rows; private development must not erase source-access obligations. Full native builds and live Android/Windows acceptance remain separate gates.
