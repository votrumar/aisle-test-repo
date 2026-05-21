from jose import jwt

_ALGORITHM = "HS256"
_MAX_TOKEN_LEN = 4096


def sign(payload: dict, secret: str) -> str:
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def verify(token: str, secret: str) -> dict:
    if len(token) > _MAX_TOKEN_LEN:
        raise ValueError("token too long")
    return jwt.decode(token, secret, algorithms=[_ALGORITHM])
