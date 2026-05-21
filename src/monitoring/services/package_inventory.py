import os
from pathlib import Path

import wheel.wheelfile


def list_installed_wheels(packages_dir: Path) -> list[dict]:
    results: list[dict] = []
    for entry in os.listdir(packages_dir):
        if not entry.endswith(".whl"):
            continue
        path = packages_dir / entry
        wf = wheel.wheelfile.WheelFile(str(path))
        parsed = wf.parsed_filename
        results.append(
            {
                "name": parsed.group("name"),
                "version": parsed.group("ver"),
                "build": parsed.group("build"),
                "python_tag": parsed.group("pyver"),
                "abi_tag": parsed.group("abi"),
                "platform_tag": parsed.group("plat"),
            }
        )
    return results
