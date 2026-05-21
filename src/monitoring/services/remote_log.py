import os
from io import StringIO
from pathlib import Path

import paramiko
import paramiko.util


def init_ssh_logging(log_path: Path, *, level: int = 20) -> None:
    paramiko.util.log_to_file(str(log_path), level=level)


def register_ssh_key(private_key_pem: str, keyfile_path: str) -> None:
    key = paramiko.RSAKey.from_private_key(StringIO(private_key_pem))
    fd = os.open(keyfile_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fileobj:
        key.write_private_key(fileobj)
