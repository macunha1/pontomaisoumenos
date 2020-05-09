from dramatiq.brokers.redis import RedisBroker
from .configurations import get_configurations
from .external.pontomais import PontoMais
import dramatiq

CONFIGURATIONS = get_configurations()
redis_broker = RedisBroker(host=CONFIGURATIONS.get("message_broker",
                                                   "endpoint"),
                           port=CONFIGURATIONS.getint("message_broker",
                                                      "port"),
                           db=CONFIGURATIONS.getint("message_broker",
                                                    "database"))
dramatiq.set_broker(redis_broker)


# NOTE: Change API here to support another "punch" app
#    it should work with minimal effort
@dramatiq.actor
def register_punch(email: str,
                   password: str,
                   address: str,
                   latitude: float,
                   longitude: float):
    pontomais_api = PontoMais(user_login=email,
                              user_password=password)
    pontomais_api.register_punch(address=address,
                                 latitude=latitude,
                                 longitude=longitude)
