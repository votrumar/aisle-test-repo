import py


def dev_workdir() -> str:
    return str(py.path.local())
