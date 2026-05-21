import gunicorn


def process_manager_version() -> str:
    return gunicorn.__version__
