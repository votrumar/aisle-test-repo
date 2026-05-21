from werkzeug.security import gen_salt


def new_request_id(length: int = 16) -> str:
    return gen_salt(length)
