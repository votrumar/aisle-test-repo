from pathlib import Path

import paramiko.util


def init_ssh_logging(log_path: Path, *, level: int = 20) -> None:
    paramiko.util.log_to_file(str(log_path), level=level)
