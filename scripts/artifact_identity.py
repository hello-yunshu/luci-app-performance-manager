#!/usr/bin/env python3
"""Resolve exact package artifacts without relying on first-match ordering.

Build workflows may expose the same APK through more than one artifact.  The
identity is the package name, expected filename (when available), and the
authoritative SHA-256 from build metadata/APK verification.  Every physical
copy is inspected; a missing copy or a conflicting digest fails closed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


class ArtifactIdentityError(RuntimeError):
    """Raised when the physical artifact set cannot prove one identity."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _roots(search_roots: Iterable[str | Path]) -> list[Path]:
    result = []
    for value in search_roots:
        path = Path(value).resolve()
        if path.exists():
            result.append(path)
    if not result:
        raise ArtifactIdentityError("no artifact search root exists")
    return result


def _candidates(package_name: str, roots: list[Path], expected_filename: str | None) -> list[Path]:
    found: set[Path] = set()
    for root in roots:
        paths = [root] if root.is_file() else root.rglob("*.apk")
        for path in paths:
            if not path.is_file():
                continue
            if expected_filename and path.name == expected_filename:
                found.add(path)
            elif not expected_filename and (
                path.name.startswith(f"{package_name}-")
                or path.name.startswith(f"{package_name}_")
            ):
                found.add(path)
    return sorted(found, key=lambda path: str(path))


def resolve_artifact(
    package_name: str,
    expected_sha: str,
    search_roots: Iterable[str | Path],
    expected_filename: str | None = None,
) -> dict:
    """Return a canonical exact artifact identity and all physical copies.

    ``canonicalPath`` is deterministic and is the only path consumers should
    stage/install.  ``copies`` is retained for audit output, so duplicate
    ownership is visible instead of being silently discarded.
    """
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ArtifactIdentityError(f"{package_name}: invalid authoritative SHA-256")
    roots = _roots(search_roots)
    candidates = _candidates(package_name, roots, expected_filename)
    if not candidates:
        suffix = f" filename={expected_filename}" if expected_filename else ""
        raise ArtifactIdentityError(f"{package_name}: no APK copy found for {expected_sha}{suffix}")

    copies = [{
        "path": str(path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    } for path in candidates]
    digests = {copy["sha256"] for copy in copies}
    if expected_sha not in digests:
        raise ArtifactIdentityError(
            f"{package_name}: no copy matches authoritative SHA {expected_sha}; "
            f"found {sorted(digests)}"
        )
    if len(digests) != 1:
        raise ArtifactIdentityError(
            f"{package_name}: conflicting APK copies found: {sorted(digests)}"
        )

    canonical = next(copy for copy in copies if copy["sha256"] == expected_sha)
    return {
        "package": package_name,
        "expectedSha256": expected_sha,
        "canonicalPath": canonical["path"],
        "copies": copies,
        "copyCount": len(copies),
        "allCopiesIdentical": len(digests) == 1,
    }
