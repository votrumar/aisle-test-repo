from jose import jwt

_ALGORITHM = "HS256"


def sign(payload: dict, secret: str) -> str:
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def verify(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=[_ALGORITHM])
