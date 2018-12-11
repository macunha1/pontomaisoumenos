from dramatiq.brokers.redis import RedisBroker
from .configurations import get_configurations
import dramatiq
import requests

CONFIGURATIONS = get_configurations()
redis_broker = RedisBroker(
    host=CONFIGURATIONS.get("message_broker", "endpoint"),
    port=CONFIGURATIONS.getint("message_broker", "port"),
    db=CONFIGURATIONS.getint("message_broker", "database"))
dramatiq.set_broker(redis_broker)


@dramatiq.actor
def count_words(url):
    response = requests.get(url)
    count = len(response.text.split(" "))
    print(f"There are {count} words at {url!r}.")

@dramatiq.actor
def register_punch():
    response = requests.get("https://www.google.com")
