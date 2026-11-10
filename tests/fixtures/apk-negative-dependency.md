# APK negative-dependency metadata fixture

`apk-negative-dependency.apk` is an unsigned, empty metadata fixture generated
with the official OpenWrt 25.12.5 SDK's apk-tools 3.0.5. It contains no Runtime
binary and cannot qualify a product, package, dependency installation, or device.

The generation command used an empty directory as `empty`:

```sh
apk mkpkg --compression none --xattrs=no \
  --info name:owner-conflict-probe --info version:1-r0 \
  --info arch:noarch --info license:MIT \
  --info 'description:Negative dependency parser fixture' \
  --info 'depends:!rill-runtime>=0' \
  --files empty --output apk-negative-dependency.apk
```

The uncompressed ADB form keeps this parser test independent of an installed
zstd CLI or Python extension. Extended filesystem attributes are excluded.

The SDK's `apk adbdump --format json` reports the dependency as
`!rill-runtime>=0`. In its ADB dependency object, field 3 includes the conflict
bit (16) and greater-or-equal mask (5). The regression prevents treating this
negative dependency as a required positive `rill-runtime` dependency.
