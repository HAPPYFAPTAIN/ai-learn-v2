from __future__ import annotations

import ctypes
from ctypes import c_int32, c_uint32, c_void_p, c_char_p, POINTER, byref
from functools import lru_cache


SERVICE = b"LearnEverything.model-connections"
ACCOUNT = b"encryption-key-v1"
NOT_FOUND = -25300
DUPLICATE = -25299


class KeychainError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _security():
    lib = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    lib.SecKeychainFindGenericPassword.argtypes = [
        c_void_p, c_uint32, c_char_p, c_uint32, c_char_p,
        POINTER(c_uint32), POINTER(c_void_p), c_void_p,
    ]
    lib.SecKeychainFindGenericPassword.restype = c_int32
    lib.SecKeychainAddGenericPassword.argtypes = [
        c_void_p, c_uint32, c_char_p, c_uint32, c_char_p,
        c_uint32, c_char_p, c_void_p,
    ]
    lib.SecKeychainAddGenericPassword.restype = c_int32
    lib.SecKeychainItemFreeContent.argtypes = [c_void_p, c_void_p]
    lib.SecKeychainItemFreeContent.restype = c_int32
    return lib


def _error(status):
    return KeychainError(f"无法访问 macOS 登录钥匙串（{status}），请解锁钥匙串并允许此应用访问后重试。")


def encryption_key(*, create=False):
    from cryptography.fernet import Fernet

    lib = _security()
    size, data = c_uint32(), c_void_p()
    status = lib.SecKeychainFindGenericPassword(
        None, len(SERVICE), SERVICE, len(ACCOUNT), ACCOUNT,
        byref(size), byref(data), None,
    )
    if status == 0:
        try:
            return ctypes.string_at(data, size.value)
        finally:
            lib.SecKeychainItemFreeContent(None, data)
    if status != NOT_FOUND:
        raise _error(status)
    if not create:
        raise KeychainError("未找到连接加密密钥，请使用保存连接时的 macOS 账户及登录钥匙串。")
    key = Fernet.generate_key()
    status = lib.SecKeychainAddGenericPassword(
        None, len(SERVICE), SERVICE, len(ACCOUNT), ACCOUNT, len(key), key, None,
    )
    if status == DUPLICATE:
        return encryption_key()
    if status != 0:
        raise _error(status)
    return key
