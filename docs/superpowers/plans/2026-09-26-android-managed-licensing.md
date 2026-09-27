# Android and managed-service licensing implementation

Goal: harden the Android client and implement server-enforced VYNX managed-service entitlements. The unmodified remote-desktop protocol and AGPL client freedoms remain intact. This is not a claim of an uncrackable client or a gated hbbr relay.

Decisions:
- Preserve PR #1's exact source tree. Work on a separate branch; no merge or production publication.
- Remove release debug boot triggers and exclude application data from backup/transfer.
- Use server-held Ed25519 signing, five-minute tokens, server-side expiry/revocation and transactional device limits.
- Bind activation and every managed request to a P-256 device key and one-use, purpose-bound, short-lived server challenges. Keep the Android private key in Android Keystore; do not store the activation code.
- Implement managed device inventory as the real protected resource. Standard peer-to-peer and relay traffic is not protected by this new service until a server-side adapter is implemented and tested.
- No signing identity, production endpoint, certificate fingerprint or payment credentials are invented.

Tasks:
1. Prove Android manifest and service-security regressions fail, implement narrow fixes, re-run tests.
2. Implement and adversarially test the licensing service: activation, device ownership, token integrity, expiry, revocation, replay, concurrent seats, rate limits and persistence.
3. Add Android Keystore signing and an optional managed-service settings page; preserve all existing remote sessions when the managed API is unconfigured.
4. Add an artifact gate for real APK identity/signature/debuggable status and document outstanding physical-device and production requirements.
5. Run existing source tests and new service tests, publish the changes on a branch/PR, run available CI and report actual outcomes without inferring unexecuted tests.
