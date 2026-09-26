# VYNX domain and private-development handoff

This profile integrates Android managed-inventory licensing (#2), Windows hardening (#1), and the exact ringbuf update (#3). It does not deploy anything or change repository visibility.

## Domain contract

| Role | Prepared destination | Current action |
|---|---|---|
| Main brand | https://vynx.com.tr/ | Existing BOT/AIO site is not overwritten. |
| VynxDesk product/downloads/source | https://vynx.com.tr/vynxdesk/ | Stage `site/vynxdesk/` as a separate directory. No binary is linked until signed and accepted. |
| VynxDesk privacy | https://vynx.com.tr/vynxdesk/privacy.html | Technical draft; controller/contact/retention must be completed and approved before production. |
| Managed inventory API | https://desk-api.vynx.com.tr | Proposed DNS/TLS/service deployment; not yet provisioned. |
| Rendezvous/relay | desk-relay.vynx.com.tr | Separate relay deployment and matching public key are required. |
| Legacy account API | None by default | Explicit compatible self-host configuration is preserved. Never point this protocol to the managed inventory API. |

`brand.json` is public non-secret product configuration. Run `python scripts/vynx_brand.py --write` after editing it, then `--check`. Generated links are consumed by desktop/mobile About, install/privacy, download and pricing navigation. Preserve upstream credits and technical documentation links. Internal `com.vynxdesk.client`, Rust crate, executable and service identifiers are intentionally unchanged to avoid upgrade/migration breakage.

The inherited upstream automatic version check sends a device fingerprint and returns RustDesk release URLs. It is now disabled for the VynxDesk-branded client, including direct calls to the checker. **This is not an implemented VYNX automatic updater.** Signed VYNX update-feed integration and clean-machine update/rollback testing remain required. Manual links target only the VynxDesk product directory.

## Server installation prerequisites

Use `services/licensing/README.md` and its hardened systemd unit. Install `licensing.env.example` as `/etc/vynxdesk/licensing.env` with mode 0600 and replace the blank source URL with the exact published corresponding-source archive. Generate the signing key on the service host; never upload it to this repository, a workflow artifact, a customer package or chat.

`desk-api.nginx.conf.example` is an additive, separate virtual host. Obtain its actual TLS certificate and DNS first. Do not replace the main site's configuration. Test `nginx -t` on the destination host before reload. The API backend stays bound to 127.0.0.1:8091. Trust forwarded headers only from the local reverse proxy. With a further Cloudflare proxy, design and verify real-IP trust separately; do not trust arbitrary inbound X-Forwarded-For.

Configure the optional Android `VYNXDESK_SERVICE_API` only after verifying service health and its public source offer. Repository/environment variables in `github-variables.env.example` are proposed values, not active deployment facts. The existing release gate still requires the real matching relay key and Android publisher certificate digest.

## Operator audit and backup

All successful issue/extend/revoke/rotate-code/release-device mutations record an `operator_events` row in the same transaction. Audit failure rolls back the mutation. Events include server timestamp, OS UID (or `local-operator` on Windows), license/device IDs and bounded operation-specific details, never enrollment codes or signing keys. A UID identifies the process account, **not an authenticated human**. This database journal is not tamper-proof against its administrator; external protected log export is a production follow-up.

```sh
# Run under the dedicated operator/service account with the protected environment.
python service.py audit --limit 100
install -d -m 0700 /var/lib/vynxdesk-licensing/backups
python operations.py /var/lib/vynxdesk-licensing/backups/licenses-20260926.db
```

The online backup API includes committed WAL data, verifies integrity, emits a SHA-256 digest, and never overwrites an existing path. On POSIX, the destination directory must be private and the file is mode 0600. A failed backup is removed. This database is confidential operational data, **not corresponding source**. Copying only the live main SQLite file while ignoring its WAL is unsupported. Back up the signing key separately to encrypted, access-controlled storage. Test restore into an isolated instance before relying on disaster recovery. Database backups temporarily written on disk must never be served from the website document root.

## Private development and selling

A private development repository is compatible with preserving recipients' AGPL rights. Making the repository private does not revoke existing public copies or relicense RustDesk-derived code. Before distributing modified binaries or operating the modified network service, provide its exact corresponding source to entitled users as required by the applicable AGPL sections. Keep LICENCE and NOTICE. A private GitHub login alone is not the customer source-distribution mechanism. Use immutable versioned archives, no production keys or customer databases, and clear source links alongside the release.

Independent business systems need their own ownership/license review; putting code in another folder or API process is not by itself a legal determination of independence. Do not advertise the current managed inventory entitlement as licensing the existing P2P/hbbr remote-control traffic. Payment verification, customer identity/recovery, relay enforcement, attestation and a signed VYNX update channel remain separate deliverables.

References: https://www.gnu.org/licenses/agpl-3.0.html (sections 6 and 13), https://www.gnu.org/licenses/gpl-faq.en.html#GPLRequireSourcePostedPublic

## Release hold

No repository visibility change, merge to master, production credential generation, DNS/site modification, live deployment, signed APK/EXE publication or customer sale is performed by this integration. Publish only after combined native/platform CI, real Android/Windows acceptance, operator privacy approval, corresponding-source availability, signing, recovery and intended paid-resource enforcement all pass. A green source/fixture test is not physical-device or commercial acceptance.
