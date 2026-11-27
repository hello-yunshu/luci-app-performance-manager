#!/usr/bin/env python3
"""Keep every OpenWrt package on the same adjacent-VERSION resolver."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "package-version.mk"
DIRECTORY_LINE = "PKG_MAKEFILE_DIR:=$(dir $(abspath $(lastword $(MAKEFILE_LIST))))"
INCLUDE_LINE = "include $(PKG_MAKEFILE_DIR)package-version.mk"


def main() -> int:
    if not HELPER.is_file():
        raise SystemExit("shared package-version.mk is missing")
    helper = HELPER.read_text(encoding="utf-8")
    for token in (
        "PKG_VERSION_FILE:=$(dir $(abspath $(lastword $(MAKEFILE_LIST))))VERSION",
        "$(wildcard $(PKG_VERSION_FILE))",
        "sed -E 's/-rc\\./_rc/'",
        "ifeq ($(PKG_VERSION),)",
    ):
        if token not in helper:
            raise SystemExit(f"shared package-version.mk is missing required behavior: {token}")

    recipes = sorted((ROOT / "package").glob("*/Makefile"))
    if not recipes:
        raise SystemExit("no package Makefiles found")
    for recipe in recipes:
        text = recipe.read_text(encoding="utf-8")
        if DIRECTORY_LINE not in text or INCLUDE_LINE not in text:
            raise SystemExit(f"{recipe.relative_to(ROOT)} does not use the shared version rule")
        if text.find(DIRECTORY_LINE) > text.find("include $(TOPDIR)/rules.mk"):
            raise SystemExit(f"{recipe.relative_to(ROOT)} resolves its directory after rules.mk")
        if "PKG_VERSION:=" in text:
            raise SystemExit(f"{recipe.relative_to(ROOT)} defines PKG_VERSION outside the shared rule")
        package_dir = recipe.parent
        for name, expected in (("VERSION", ROOT / "VERSION"), ("package-version.mk", HELPER)):
            path = package_dir / name
            if not path.is_file() or path.resolve() != expected.resolve():
                raise SystemExit(f"{recipe.relative_to(ROOT)} has an invalid {name} link")
    print(f"shared VERSION rule passed for {len(recipes)} package recipes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
