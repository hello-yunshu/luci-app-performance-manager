"""Run an unmodified package payload with an optional explicit musl loader.

Only verification harnesses use this helper. Payload hashing always applies to
binary itself, independently of the command used to load it on a Linux host.
"""
from pathlib import Path
import os


def runtime_command(binary: Path) -> list[str]:
    loader = os.environ.get("RILL_TEST_LOADER")
    libraries = os.environ.get("RILL_TEST_LIBRARY_PATH")
    if bool(loader) != bool(libraries):
        raise ValueError("explicit Runtime loader and library path must be supplied together")
    if not loader:
        return [str(binary)]
    path = Path(loader)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Runtime test loader must name an existing absolute file")
    if any(not Path(item).is_absolute() or not Path(item).is_dir() for item in libraries.split(":")):
        raise ValueError("Runtime test library paths must be existing absolute directories")
    return [str(path), "--library-path", libraries, str(binary)]
