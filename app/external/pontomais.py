import requests
from ..configurations import get_logger

LOGGER = get_logger()


class PontoMais:
    def __init__(self,
                 user_email,
                 user_password):
        self.user_email = user_email
        self.user_password = user_password
        self.token, self.client_id = self.authenticate()

    def authenticate(self) -> (str, str):
        auth_endpoint = "http://api.pontomaisweb.com.br/api/auth/sign_in"
        auth_headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:65.0) Gecko/20100101 Firefox/65.0",
            "Content-Type": "application/json",
            "X-Requested-With": "br.com.pontomais.pontomais"
        }
        auth_credentials = {
            "email": self.user_email,
            "password": self.user_password
        }

        response = requests.post(auth_endpoint,
                                 headers=auth_headers,
                                 data=auth_credentials)

        if response.content and not response.raise_for_status():
            LOGGER.debug(f"PontoMais.authenticate response body {response.body}")
            response_json = response.json()
            return response_json.get("token"), response_json.get("client_id")
        LOGGER.error(f"PontoMais.authenticate with error {response.status_code}")

    def register_punch(self, address: str, latitude: int, longitude: int) -> None:
        punch_endpoint = "https://api.pontomaisweb.com.br/api/time_cards/register"

        punch_data = {
            "_path": "/meu_ponto/registro_de_ponto",
            "time_card": {
                "accuracy": 600,
                "accuracy_method": True,
                "address": address,
                "latitude": latitude,
                "location_edited": False,
                "longitude": longitude,
                "original_address": address,
                "original_latitude": latitude - 10,
                "original_longitude": longitude + 10,
                "reference_id": None
            }
        }

        punch_headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:65.0) Gecko/20100101 Firefox/65.0",
            "Content-Type": "application/json",
            "X-Requested-With": "br.com.pontomais.pontomais",
            "token-type": "Bearer",
            "uid": self.user_email,
            "access-token": self.token,
            "client": self.client_id
        }

        response = requests.post(punch_endpoint,
                                 headers=punch_headers,
                                 data=punch_data,
                                 verify=False)

        if response.content and not response.raise_for_status():
            response_json = response.json()
            if response_json.get("untreated_time_card"):
                punch_created_at = response_json.get("untreated_time_card").get("created_at")
                LOGGER.info(f"PontoMais.register_punch created a time card at {punch_created_at}")
