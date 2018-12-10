from Crypto.PublicKey import RSA
from Crypto import Random


class EncryptionHandler(object):
    def __init__(self):
        _random_gen = Random.new().read
        key = RSA.generate(2048, _random_gen)
        key.publickey.exportKey()  # Exports Public RSA key

    def encrypt(self, value: str):
        return self.key.encrypt(value.encode(), 32)

    def decrypt(self, value: tuple):
        return self.key.decrypt(value)

    def save_key(self):
        # TODO: Save private key to the database
        # private_key = key.exportKey()  # Exports Private RSA key
        # rsa(private_key=private_key)
        # rsa.save()
        pass

    def read_key(self):
        # TODO: Get the private key from the database
        # RSA.select(key).where(User.id=="lalala")
        # RSA.importKey(private_key)  # Reload an exported RSA key
        pass
