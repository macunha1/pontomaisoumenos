from Crypto.PublicKey import RSA
from Crypto import Random
from .configurations import get_logger

LOGGER = get_logger()


class EncryptionHandler:
    def __init__(self, private_key: bytes = None):
        if not private_key:
            __random_gen = Random.new().read
            self.key = RSA.generate(2048, __random_gen)
        else:
            self.load_key(value=private_key)

    def encrypt(self, value: str) -> bytes:
        return self.key.encrypt(value.encode(), 32)[0]

    def decrypt(self, value: tuple) -> str:
        return self.key.decrypt(value).decode()

    # Exports Private RSA key
    def get_key(self) -> str:
        return self.key.exportKey().decode()

    def load_key(self,
                 value: str):
        if isinstance(value, bytes):
            value = value.decode()
        self.key = RSA.importKey(value)  # Reload an exported RSA key
