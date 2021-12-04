import uuid
import requests
import json
from ..configurations import get_logger

LOGGER = get_logger()

# Ponto Mais base API URL
BASE_URL = 'https://api.pontomais.com.br'


class PontoMais:
    def __init__(self, user_login, user_password):
        self.login = user_login
        self.user_password = user_password
        self.uuid = str(uuid.uuid1())
        self.token, self.client_id, self.expiry = self.authenticate()

    def authenticate(self) -> (str, str):
        auth_endpoint = "{url}/api/auth/sign_in".format(url=BASE_URL)
        auth_credentials = {
            "login": self.login,
            "password": self.user_password
        }

        response = requests.post(auth_endpoint,
                                 data=auth_credentials)

        if response.content and not response.raise_for_status():
            response_json = response.json()
            LOGGER.debug("PontoMais.authenticate response body %s"
                         % response_json.get('success'))
            return (response_json.get("token"),
                    response_json.get("client_id"),
                    response_json.get("expiry"))

        LOGGER.error("PontoMais.authenticate with error %s"
                     % response.status_code)

    def register_punch(self, address: str,
                       latitude: int,
                       longitude: int) -> None:
        punch_endpoint = f"{BASE_URL}/api/time_cards/register"

        punch_data = {
            '_path': '/meu_ponto/registro_de_ponto',
            '_device': {
                'manufacturer': None,
                'model': None,
                'uuid': None,
                'version': None,
                'browser': {
                    'name': 'Firefox',
                    'version': '67.0',
                    'versionSearchString': 'Firefox'
                }
            },
            '_appVersion': '0.10.32',
            'time_card': {
                'latitude': latitude,
                'longitude': longitude,
                'address': address,
                'reference_id': None,
                'original_latitude': latitude,
                'original_longitude': longitude,
                'original_address': address,
                'location_edited': True
            },
        }

        punch_headers = {
            'Host': 'api.pontomais.com.br',
            'Content-Type': 'application/json;charset=utf-8',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0',  # noqa: E501
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'https://app.pontomaisweb.com.br',
            'Referer': 'https://app.pontomaisweb.com.br//',
            'token-type': 'Bearer',
            'uid': self.login,
            'uuid': self.uuid,
            'access-token': self.token,
            'expiry': self.expiry,
            'Api-Version': '2',
            'client': self.client_id,
            'content-type': 'application/json'
        }

        response = requests.post(
            punch_endpoint,
            headers=punch_headers,
            data=json.dumps(punch_data),
            verify=False)

        if response.content and not response.raise_for_status():
            response_json = response.json()
            if response_json.get("untreated_time_card"):
                punch_created_at = response_json.get("untreated_time_card") \
                                                .get("created_at")
                LOGGER.info("PontoMais.register_punch created a time card at %s"
                            % punch_created_at)
