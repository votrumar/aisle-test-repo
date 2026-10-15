import fcntl
import hashlib
import os
import stat
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from uuid import uuid4

import paramiko
import paramiko.util
from cryptography.fernet import Fernet
from paramiko.ssh_exception import SSHException

from ..config import settings

_REMOTE_SENSOR_KEY_DIR = Path.home() / ".monitoring" / "remote-sensor-keys"
_MAX_REMOTE_SENSOR_KEYS = 4096
_MAX_HOST_LEN = 255
_MAX_USERNAME_LEN = 64
_MAX_PRIVATE_KEY_PEM_LEN = 16_384
_MIN_RSA_BITS = 2048


class RemoteSensorKeyError(ValueError):
    def __init__(self, detail: str, status_code: int = 422) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def init_ssh_logging(log_path: Path, *, level: int = 20) -> None:
    paramiko.util.log_to_file(str(log_path), level=level)


def _remote_sensor_key_cipher() -> Fernet:
    return Fernet(settings.remote_sensor_key_encryption_secret.get_secret_value().encode("utf-8"))


def _remote_sensor_key_dir() -> Path:
    key_dir = _REMOTE_SENSOR_KEY_DIR.expanduser()
    key_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    directory_stat = os.lstat(key_dir)
    if not stat.S_ISDIR(directory_stat.st_mode):
        raise RemoteSensorKeyError("remote sensor key directory must be a real directory", status_code=500)
    if hasattr(os, "geteuid") and directory_stat.st_uid != os.geteuid():
        raise RemoteSensorKeyError("remote sensor key directory owner is invalid", status_code=500)

    os.chmod(key_dir, 0o700)
    directory_mode = stat.S_IMODE(os.lstat(key_dir).st_mode)
    if directory_mode != 0o700:
        raise RemoteSensorKeyError("remote sensor key directory permissions are invalid", status_code=500)

    return key_dir.resolve()


def _validate_remote_sensor_identity(host: str, username: str) -> None:
    if len(host) > _MAX_HOST_LEN:
        raise RemoteSensorKeyError("host is too long")
    if len(username) > _MAX_USERNAME_LEN:
        raise RemoteSensorKeyError("username is too long")


@contextmanager
def _key_directory_lock(key_dir: Path):
    lock_path = key_dir / ".key_budget.lock"
    flags = os.O_WRONLY | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    fd = os.open(lock_path, flags, 0o600)
    with os.fdopen(fd, "w") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def remote_sensor_key_path(host: str, username: str) -> Path:
    _validate_remote_sensor_identity(host, username)
    key_dir = _remote_sensor_key_dir()
    sensor_id = hashlib.sha256(f"{username}\0{host}".encode("utf-8")).hexdigest()
    key_path = key_dir / f"{sensor_id}.pem.enc"
    resolved = key_path.resolve(strict=False)
    if not resolved.is_relative_to(key_dir):
        raise RemoteSensorKeyError("managed key path is invalid", status_code=500)
    return key_path


def _validate_key_budget(key_dir: Path, key_path: Path) -> None:
    if key_path.exists() or key_path.is_symlink():
        return

    managed_key_count = sum(1 for candidate in key_dir.iterdir() if candidate.name.endswith(".pem.enc"))
    if managed_key_count >= _MAX_REMOTE_SENSOR_KEYS:
        raise RemoteSensorKeyError("remote sensor key limit reached", status_code=429)


def _serialize_private_key(private_key_pem: str) -> str:
    if len(private_key_pem) > _MAX_PRIVATE_KEY_PEM_LEN:
        raise RemoteSensorKeyError("private key too large", status_code=413)

    try:
        key = paramiko.RSAKey.from_private_key(StringIO(private_key_pem))
    except (SSHException, ValueError, TypeError) as exc:
        raise RemoteSensorKeyError("invalid private key") from exc

    if key.get_bits() < _MIN_RSA_BITS:
        raise RemoteSensorKeyError(f"RSA key too weak: minimum size is {_MIN_RSA_BITS} bits")

    serialized = StringIO()
    key.write_private_key(serialized)
    return serialized.getvalue()


def _encrypt_private_key(private_key_pem: str) -> bytes:
    return _remote_sensor_key_cipher().encrypt(private_key_pem.encode("utf-8"))


def _decrypt_private_key(encrypted_private_key: bytes) -> str:
    return _remote_sensor_key_cipher().decrypt(encrypted_private_key).decode("utf-8")


def _create_private_key_file(key_path: Path, encrypted_private_key: bytes) -> None:
    with _key_directory_lock(key_path.parent):
        _validate_key_budget(key_path.parent, key_path)

        temp_path = key_path.parent / f".{key_path.name}.{uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        fd = os.open(temp_path, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as fileobj:
                fileobj.write(encrypted_private_key)
            os.replace(temp_path, key_path)
        except Exception:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
            raise


def register_ssh_key(private_key_pem: str, host: str, username: str) -> Path:
    serialized = _serialize_private_key(private_key_pem)
    encrypted_private_key = _encrypt_private_key(serialized)
    key_path = remote_sensor_key_path(host, username)
    _create_private_key_file(key_path, encrypted_private_key)
    return key_path


def read_registered_ssh_key(host: str, username: str) -> str:
    return _decrypt_private_key(remote_sensor_key_path(host, username).read_bytes())
