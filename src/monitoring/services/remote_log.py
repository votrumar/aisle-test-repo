import errno
import os
import stat
from io import StringIO
from pathlib import Path

import paramiko
import paramiko.util

_REMOTE_SENSOR_KEYS_DIR = Path(
    os.environ.get("MONITORING_REMOTE_SENSOR_KEYS_DIR", "/var/lib/monitoring/remote-sensor-keys")
)
_INVALID_PATH_SEGMENTS = {"", ".", ".."}
_MAX_KEYFILE_PATH_LEN = 255
_MAX_KEYFILE_PATH_DEPTH = 8
# The confinement logic relies on opening directories and the final file without
# following symlinks. If the platform cannot enforce those flags, key storage is
# disabled rather than silently weakening the boundary.
_REQUIRED_OPEN_FLAGS = ("O_DIRECTORY", "O_NOFOLLOW")
_MISSING_OPEN_FLAGS = tuple(name for name in _REQUIRED_OPEN_FLAGS if not hasattr(os, name))
if _MISSING_OPEN_FLAGS:
    raise RuntimeError(
        "secure remote sensor key storage requires: " + ", ".join(_MISSING_OPEN_FLAGS)
    )
_DIR_OPEN_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE_OPEN_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW


def init_ssh_logging(log_path: Path, *, level: int = 20) -> None:
    paramiko.util.log_to_file(str(log_path), level=level)


def _validated_keyfile_parts(keyfile_path: str) -> tuple[str, ...]:
    # Keep client-controlled paths simple and bounded before any filesystem or
    # key-parsing work happens.
    if len(keyfile_path) > _MAX_KEYFILE_PATH_LEN:
        raise ValueError("keyfile_path too long")

    candidate = Path(keyfile_path)
    if candidate.is_absolute():
        raise ValueError("keyfile_path must be relative")

    parts = candidate.parts
    if not parts or any(part in _INVALID_PATH_SEGMENTS for part in parts):
        raise ValueError("keyfile_path must not contain empty, '.' or '..' segments")
    if len(parts) > _MAX_KEYFILE_PATH_DEPTH:
        raise ValueError("keyfile_path too deep")
    return parts


def _assert_private_dir(fd: int, *, path_hint: Path) -> None:
    # Existing directories are reused only when they remain private to the
    # service account; otherwise a local user could tamper with key management.
    details = os.fstat(fd)
    if not stat.S_ISDIR(details.st_mode):
        raise NotADirectoryError(f"{path_hint} is not a directory")
    if details.st_uid != os.getuid():
        raise PermissionError(f"insecure ownership for {path_hint}")
    if stat.S_IMODE(details.st_mode) & 0o077:
        raise PermissionError(f"insecure permissions for {path_hint}")


def _open_confined_keyfile(parts: tuple[str, ...]) -> int:
    _REMOTE_SENSOR_KEYS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    try:
        current_fd = os.open(_REMOTE_SENSOR_KEYS_DIR, _DIR_OPEN_FLAGS)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("remote sensor key directory must not be a symlink") from exc
        raise

    current_path = _REMOTE_SENSOR_KEYS_DIR
    try:
        _assert_private_dir(current_fd, path_hint=current_path)
        # Walk one component at a time so every intermediate directory is both
        # inside the trusted tree and verified before descending further.
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o700, dir_fd=current_fd)
            except FileExistsError:
                pass

            try:
                next_fd = os.open(part, _DIR_OPEN_FLAGS, dir_fd=current_fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise ValueError("keyfile_path must not traverse symlinks") from exc
                raise

            next_path = current_path / part
            try:
                _assert_private_dir(next_fd, path_hint=next_path)
            except Exception:
                os.close(next_fd)
                raise

            os.close(current_fd)
            current_fd = next_fd
            current_path = next_path

        try:
            return os.open(parts[-1], _FILE_OPEN_FLAGS, 0o600, dir_fd=current_fd)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ValueError("keyfile_path must not be a symlink") from exc
            raise
    finally:
        os.close(current_fd)


def register_ssh_key(private_key_pem: str, keyfile_path: str) -> None:
    # Validate the path before parsing the PEM so obviously bad requests fail
    # fast and do not spend time inside Paramiko.
    parts = _validated_keyfile_parts(keyfile_path)
    key = paramiko.RSAKey.from_private_key(StringIO(private_key_pem))
    fd = _open_confined_keyfile(parts)
    with os.fdopen(fd, "w") as fileobj:
        key.write_private_key(fileobj)
