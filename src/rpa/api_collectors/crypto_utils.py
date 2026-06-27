"""
API 凭证加密工具 — AES-256-GCM
密钥来源: 环境变量 RPA_API_ENCRYPTION_KEY
存储格式: IV(12bytes) + Ciphertext + Tag(16bytes)，Base64 编码
"""
import base64
import os
import sys

ENCRYPTION_KEY = None


def _get_key():
    """懒加载加密密钥，从环境变量读取"""
    global ENCRYPTION_KEY
    if ENCRYPTION_KEY is None:
        key_str = os.environ.get("RPA_API_ENCRYPTION_KEY", "")
        if not key_str or len(key_str) < 32:
            # 未配置密钥时生成随机密钥（重启后会变化，仅用于开发环境）
            key_str = base64.b64encode(os.urandom(32)).decode()
            print("[API Crypto] 未配置 RPA_API_ENCRYPTION_KEY，使用随机密钥（重启后失效）", file=sys.stderr)
        try:
            ENCRYPTION_KEY = base64.b64decode(key_str) if len(key_str) >= 44 else key_str.encode()
        except Exception:
            ENCRYPTION_KEY = key_str.encode()
    return ENCRYPTION_KEY


def encrypt(plaintext: str, key_version: int = 1) -> str:
    """加密明文，返回 Base64 编码的密文"""
    if not plaintext:
        return ""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(_get_key())
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt(encoded: str) -> str:
    """解密密文，返回明文"""
    if not encoded:
        return ""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(_get_key())
    raw = base64.b64decode(encoded)
    nonce, ciphertext = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode()


def mask(text: str, show_prefix: int = 4, show_suffix: int = 0) -> str:
    """脱敏展示"""
    if not text:
        return ""
    if len(text) <= show_prefix + show_suffix + 3:
        return text[:show_prefix] + "***"
    result = text[:show_prefix] + "***"
    if show_suffix > 0:
        result += text[-show_suffix:]
    return result