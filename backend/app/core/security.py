import hashlib
import hmac
import secrets


def _derive(password, salt):
    return hashlib.scrypt(
        password.encode(), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024**2
    ).hex()


def hash_password(password):
    salt = secrets.token_bytes(16)
    return f"scrypt:{salt.hex()}:{_derive(password, salt)}"


def verify_password(password, encoded):
    try:
        method, salt, expected = encoded.split(":")
        if method != "scrypt":
            return False
        return hmac.compare_digest(_derive(password, bytes.fromhex(salt)), expected)
    except (ValueError, AttributeError):
        return False


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()
