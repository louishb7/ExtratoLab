"""Publish complete exports atomically without replacing existing files."""
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def write_export(output: Path, contents: str, *, encoding: str) -> None:
    payload = contents.encode(encoding)
    temporary = None
    try:
        # Same filesystem, owner-only POSIX temporary; NTFS supports hard links.
        with NamedTemporaryFile(dir=output.parent, prefix=".pdf-to-ofx-", delete=False) as file:
            temporary = Path(file.name)
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        # Atomic publication refuses existing files (including dangling links).
        # Unsupported filesystems fail closed; no non-atomic fallback.
        output.hardlink_to(temporary)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_ofx(output: Path, contents: str) -> None:
    write_export(output, contents, encoding="ascii")


def write_csv(output: Path, contents: str) -> None:
    write_export(output, contents, encoding="utf-8")
