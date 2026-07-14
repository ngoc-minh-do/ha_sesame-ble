"""Cryptographic primitives for Sesame OS2 BLE protocol."""

import secrets

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESCCM


class AppKey:
    def __new__(cls):
        raise NotImplementedError(
            "Use AppKeyFactory.get_instance() instead."
        )

    @classmethod
    def __private_new__(cls):
        return cls.__private_init__(super().__new__(cls))

    @classmethod
    def __private_init__(cls, self) -> None:
        self._secretKey = ec.generate_private_key(ec.SECP256R1()).private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self._appToken = secrets.token_bytes(4)
        return self

    def __init__(self) -> None:
        self._secretKey: bytes
        self._appToken: bytes

    def getAppToken(self) -> bytes:
        return self._appToken

    def getPubkey(self) -> bytes:
        pk = (
            serialization.load_der_private_key(self._secretKey, password=None)
            .public_key()
            .public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        return pk[27:]

    def ecdh(self, remote_pubkey: bytes) -> bytes:
        fixed_header = bytes.fromhex(
            "3059301306072a8648ce3d020106082a8648ce3d03010703420004"
        )
        remote_pk: ec.EllipticCurvePublicKey = serialization.load_der_public_key(
            fixed_header + remote_pubkey
        )
        local_sk: ec.EllipticCurvePrivateKey = serialization.load_der_private_key(
            self._secretKey, password=None
        )
        return local_sk.exchange(ec.ECDH(), remote_pk)


class AppKeyFactory:
    _instance = None

    @classmethod
    def get_instance(cls) -> AppKey:
        if cls._instance is None:
            cls._instance = AppKey.__private_new__()
        return cls._instance


class BleCipher:
    def __init__(self, session_key: bytes, session_token: bytes) -> None:
        self._session_key = session_key
        self._session_token = session_token
        self._decryptCounter = 0
        self._encryptCounter = 0

    def decrypt(self, cipher_bytes: bytes) -> bytes:
        header = (self._decryptCounter & 549755813887).to_bytes(5, "little")
        nonce = header + self._session_token
        self._decryptCounter += 1
        aesccm = AESCCM(key=self._session_key, tag_length=4)
        return aesccm.decrypt(
            nonce=nonce, data=cipher_bytes, associated_data=b"\x00"
        )

    def encrypt(self, plain_bytes: bytes) -> bytes:
        header = (self._encryptCounter | 549755813888).to_bytes(5, "little")
        nonce = header + self._session_token
        self._encryptCounter += 1
        aesccm = AESCCM(key=self._session_key, tag_length=4)
        return aesccm.encrypt(
            nonce=nonce, data=plain_bytes, associated_data=b"\x00"
        )
