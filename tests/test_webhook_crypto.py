import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from monitoring.services.webhook import encrypt_payload


def test_encrypt_payload_roundtrip(monkeypatch):
    iv = b"\x01" * 16
    monkeypatch.setattr(os, "urandom", lambda n: iv if n == 16 else b"\x00" * n)

    key = b"k" * 32
    plaintext = b"{\"hello\": \"world\"}"

    ciphertext = encrypt_payload(plaintext, key)
    assert ciphertext[:16] == iv

    encrypted = ciphertext[16:]
    assert len(encrypted) % 16 == 0

    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()

    # encrypt_payload uses a simple zero-padding scheme.
    assert padded.startswith(plaintext)
    assert padded[len(plaintext) :] == b"\x00" * (-len(plaintext) % 16)
