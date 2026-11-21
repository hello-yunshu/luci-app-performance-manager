# PM and shared Rill package integration status

PM's public package is `luci-app-performance-manager-all` only. It contains PM Core, LuCI, translations, Rill glue, upgrade rules, and `/usr/share/performance-manager/rill-runtime-compat.json`; it does not own `/usr/bin/rill-runtime`. The public package hard-depends on the canonical feed's `rill-runtime` and `rill-runtime-manager` packages.

The Rill page calls only the fixed `rill-runtime-manager` RPC object and fixed package names. The package manager service owns the allowlist, feed operations, and Runtime binary. PM ACL grants status read plus the three package-management actions. Unsupported devices and a missing manager stay visible as recoverable UI states. Existing PM split owners and legacy `rill-runtime-preview` are conflicts; install is rejected until an administrator plans and completes migration, and PM never silently removes packages.

The public package identity remains `luci-app-performance-manager-all`, so an installed all-in-one package follows a same-name package upgrade. Historical full packages bundled `/usr/bin/rill-runtime`; the new package transfers that path to `rill-runtime`. The existing APK upgrade gate uses a private synthetic lower-version package with that owned Runtime path and checks that config survives and Runtime remains after PM removal. It is not an artifact from a historical public release. Equivalent opkg migration on OpenWrt 24.10 is not yet qualified.

For an old split installation, back up `/etc/config/performance-manager` and `/etc/performance-manager/`, then remove `performance-manager-rill`, `luci-app-performance-manager`, and `performance-manager` in dependency-safe order before installing the unified package. Legacy Preview Runtime is a hard conflict: inspect its other consumers and plan their migration before removing it. Do not force a file overwrite. `/etc/config/performance-manager` is a package conffile, while the Core and Rill keep rules preserve `/etc/performance-manager/` and Rill state during sysupgrade. The package removal hook runs PM-owned lease cleanup and does not purge those config/data paths.

## Current compatibility pin

The PM Core currently requires Runtime version `1.5.6` exactly. Its installed consumer manifest therefore declares `minVersion: 1.5.6` and exclusive `maxVersionExclusive: 1.5.7`. Widen this range only in a PM release whose Core accepts the wider Runtime range.

## Upstream release lock is pending

`contracts/rill-runtime.json` still points to the previously published immutable Rill package commit. That commit predates the local `rill-runtime-manager` recipe and does not provide the new 24.10.8/25.12.6 × six-architecture qualification matrix. The PM workflow does not substitute an unpushed local Rill tree or invent a commit: it requires an explicit `RILL_PACKAGE_COMMIT` (workflow input or repository variable), requires exact equality with the contract lock, and fails closed if the checked out commit lacks either package recipe.

Before that workflow can pass, publish the Rill manager change, update the contract lock from a real immutable Rill commit, and publish qualified Runtime artifacts for the exact package format, release, and architecture pairs in `contracts/openwrt-native-targets.json`. CI then builds the manager recipe into the same SDK package graph and verifies the PM package's metadata dependencies and shared Runtime ownership.
