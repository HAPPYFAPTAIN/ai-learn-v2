import ctypes
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet

from learning_ext import macos_keychain as keychain


@pytest.fixture
def native(monkeypatch):
    lib = Mock()
    monkeypatch.setattr(keychain, "_security", lambda: lib)
    return lib


def found(key):
    buffer = ctypes.create_string_buffer(key)

    def lookup(*args):
        ctypes.cast(args[5], ctypes.POINTER(ctypes.c_uint32))[0] = len(key)
        ctypes.cast(args[6], ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.cast(buffer, ctypes.c_void_p)
        return 0
    return lookup


def test_existing_key_is_read_and_native_memory_freed(native):
    key = Fernet.generate_key()
    native.SecKeychainFindGenericPassword.side_effect = found(key)
    assert keychain.encryption_key() == key
    native.SecKeychainItemFreeContent.assert_called_once()
    native.SecKeychainAddGenericPassword.assert_not_called()


def test_missing_key_is_only_created_for_new_store(native):
    native.SecKeychainFindGenericPassword.return_value = keychain.NOT_FOUND
    with pytest.raises(keychain.KeychainError, match="未找到"):
        keychain.encryption_key()
    native.SecKeychainAddGenericPassword.assert_not_called()
    native.SecKeychainAddGenericPassword.return_value = 0
    key = keychain.encryption_key(create=True)
    Fernet(key)
    assert native.SecKeychainAddGenericPassword.call_args.args[6] == key


def test_simultaneous_creation_reloads_winning_key(native):
    key = Fernet.generate_key()
    def lookup(*args):
        return found(key)(*args)
    native.SecKeychainAddGenericPassword.return_value = keychain.DUPLICATE
    calls = iter([False, True])
    native.SecKeychainFindGenericPassword.side_effect = lambda *args: lookup(*args) if next(calls) else keychain.NOT_FOUND
    assert keychain.encryption_key(create=True) == key


@pytest.mark.parametrize("stage", ["read", "write"])
def test_access_denial_never_falls_back_to_plaintext(native, stage):
    native.SecKeychainFindGenericPassword.return_value = -25308 if stage == "read" else keychain.NOT_FOUND
    native.SecKeychainAddGenericPassword.return_value = -25308
    with pytest.raises(keychain.KeychainError, match="解锁钥匙串"):
        keychain.encryption_key(create=True)
