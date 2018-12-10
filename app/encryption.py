from Crypto.PublicKey import RSA
from Crypto import Random
from base64 import b64encode, b64decode


class EncryptionHandler:
    def __init__(self, private_key: bytes = None):
        if not private_key:
            __random_gen = Random.new().read
            self.key = RSA.generate(2048, __random_gen)
        else:
            self.key = self.load_key(value=private_key)

    def encrypt(self, value: str):
        return self.key.encrypt(value.encode(), 32)

    def decrypt(self, value: tuple):
        return self.key.decrypt(value)

    def get_key(self):
        _base64 = b64encode(self.key.exportKey())
        return _base64  # Exports Private RSA key

    def load_key(self,
                 value: bytes):
        _key = b64decode(value)
        self.key = RSA.importKey(_key)  # Reload an exported RSA key
