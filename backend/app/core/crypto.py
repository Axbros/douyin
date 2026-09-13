import base64

from cryptography.fernet import Fernet

from app.core.config import get_settings


def storage_cipher() -> Fernet:
    raw = get_settings().storage_state_encryption_key
    # 32-byte base64 is the format required by Fernet.
    try:
        return Fernet(raw.encode())
    except Exception as exc:
        raise RuntimeError("STORAGE_STATE_ENCRYPTION_KEY 必须是 Fernet 密钥") from exc


def encrypt_storage_state(state: dict) -> bytes:
    import json
    return storage_cipher().encrypt(json.dumps(state, ensure_ascii=False).encode())


def generate_fernet_key() -> str:
    return Fernet.generate_key().decode()
