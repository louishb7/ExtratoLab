"""Publish complete exports atomically without replacing existing files."""
import os
import errno
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile


def _rename_no_replace(source: Path, destination: Path) -> None:
    """Use only native operations with an exclusive atomic creation contract.

    POSIX rename replaces files, so it is never a fallback. Unsupported Linux
    kernels/filesystems and other platforms keep failing closed.
    """
    if sys.platform == "win32":
        # Python's Windows rename refuses an existing destination, unlike POSIX.
        os.rename(source, destination)
        return
    if not sys.platform.startswith("linux"):
        raise OSError(errno.ENOTSUP, "Exclusive atomic rename is unavailable.")
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    if rename is None:
        raise OSError(errno.ENOTSUP, "Exclusive atomic rename is unavailable.")
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    # AT_FDCWD, RENAME_NOREPLACE. Both paths are on the temporary's filesystem.
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1):
        error = ctypes.get_errno()
        raise OSError(error, "Exclusive atomic publication failed.")


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
        try:
            output.hardlink_to(temporary)
        except OSError as error:
            if error.errno not in {errno.EOPNOTSUPP, errno.ENOTSUP, errno.ENOSYS, errno.EPERM}:
                raise
            _rename_no_replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_ofx(output: Path, contents: str) -> None:
    write_export(output, contents, encoding="ascii")


def write_csv(output: Path, contents: str) -> None:
    write_export(output, contents, encoding="utf-8")
