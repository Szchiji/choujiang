"""Bot Token 加密存储（简单 Fernet，密钥派生自 WEBHOOK_SECRET）"""
import base64
import hashlib
from cryptography.fernet import Fernet
from app.config import settings


def _get_fernet() -> Fernet:
    key = hashlib.sha256(settings.WEBHOOK_SECRET.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_token(token: str) -> str:
    if not token or token.startswith("enc:"):
        return token
    return "enc:" + _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(token: str) -> str:
    if not token or not token.startswith("enc:"):
        return token
    try:
        return _get_fernet().decrypt(token[4:].encode()).decode()
    except Exception:
        return token
