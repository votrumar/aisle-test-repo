from pathlib import Path


_DOCKERFILE = Path(__file__).resolve().parent.parent / "Dockerfile"


def test_dockerfile_runs_as_non_root_user():
    user_directives = [
        line.strip()
        for line in _DOCKERFILE.read_text().splitlines()
        if line.strip().upper().startswith("USER ")
    ]

    assert user_directives, "Dockerfile must declare a runtime USER"

    last_user = user_directives[-1].split(maxsplit=1)[1].strip()
    primary_user = last_user.split(":", maxsplit=1)[0].strip().lower()

    assert primary_user not in {"root", "0"}, "Dockerfile must not run as root"
