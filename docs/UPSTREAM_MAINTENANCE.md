# Upstream and Submodule Maintenance

## Source of Truth

The root repository starts at the annotated tag
`vynxdesk-baseline-2026-09-15` and has the official RustDesk source configured
as the `upstream` remote. Every product change belongs in a normal root commit
after that tag.

Before an upstream refresh, create a dedicated branch and inspect the exact
range:

```sh
git fetch --no-recurse-submodules upstream master --tags
git switch -c upstream-sync/<date>
git log --oneline master..upstream/master
# The product repository was imported without upstream history, so compare trees
# directly until a common ancestor is deliberately established.
git diff --stat master upstream/master
```

The root fetch may still report a missing upstream submodule object when the
remote's current gitlink is not available from the public submodule remote.
Treat that as an infrastructure finding: keep the fetched root ref, record the
gitlink SHA, and do not merge or rewrite the local `hbb_common` checkout until
the exact object is available from a controlled fork.

Apply protocol, transport, and dependency changes in small commits. Run the
relevant fixture and session tests after each transport update. Do not merge an
unreviewed upstream range into the product branch.

## Custom hbb_common State

The current `libs/hbb_common` worktree includes VynxDesk-specific changes and
is at local commit `47d560448682a9772b36f9003d8db9537a987a86`. Its public
upstream parent is `3d6fb2c397f2a9a717440f7e29afed5ab5f5dc03`.

Before this root repository is pushed to a remote CI service, push that custom
commit to a VynxDesk-controlled `hbb_common` fork and update the submodule URL
in `.gitmodules` to that fork. A root gitlink pointing at a local-only submodule
commit cannot be cloned by a remote runner. This is a release infrastructure
prerequisite, not a source-code workaround.

The nested `libs/hwcodec/externals` dependency is explicitly registered as a
submodule and ignores only untracked build markers. Tracked changes inside that
submodule must still be reviewed and committed normally.

## Version Contract

`toolchain-versions.toml` is the version source for application Rust, legacy
Sciter Rust, Flutter, Flutter ARM64, Flutter bridge generation, vcpkg, and the
dependency audit tool. Run the following before changing a versioned build
component:

```sh
python scripts/check_build_contract.py
```

The checker validates the root manifest, CI workflows, Flutter bridge workflow,
vcpkg manifest, Docker build, and developer README. Update all dependent
values in one reviewed change, then regenerate or validate generated bridge
artifacts with the matching bridge workflow.

## Security Updates

Run `cargo audit` after every dependency update. The commercial release gate
also runs it. Security advisories must be remediated in the lockfile; do not add
an ignore entry for an active vulnerability simply to make the gate green.

Warnings for unmaintained or yanked transitive dependencies remain visible in
the audit output and should be removed through upstream or dependency updates
in separate, compatibility-tested changes.
