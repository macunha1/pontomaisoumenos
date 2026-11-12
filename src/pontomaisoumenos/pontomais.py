"""Async adapter for the existing PontoMais API contract."""

import asyncio
from typing import TypedDict
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .settings import Settings


class Browser(TypedDict):
    name: str
    version: str
    versionSearchString: str


class Device(TypedDict):
    manufacturer: None
    model: None
    uuid: None
    version: None
    browser: Browser


class TimeCardSubmission(TypedDict):
    latitude: float
    longitude: float
    address: str
    reference_id: None
    original_latitude: float
    original_longitude: float
    original_address: str
    location_edited: bool


class PunchSubmission(TypedDict):
    _path: str
    _device: Device
    _appVersion: str
    time_card: TimeCardSubmission


class Authentication(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    token: str = Field(min_length=1)
    client_id: str = Field(min_length=1)
    expiry: str = Field(min_length=1)


class TimeCard(BaseModel):
    created_at: str = Field(min_length=1)


class PunchResponse(BaseModel):
    untreated_time_card: TimeCard


class RetryablePunchError(Exception):
    """The remote submission is known not to have taken effect."""


class PermanentPunchError(Exception):
    pass


class UncertainPunchError(Exception):
    """The server might have accepted the punch; reconciliation is required."""


class PontoMais:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self.settings = settings
        self.http = http
        self.authentication: Authentication | None = None
        self.authentication_lock = asyncio.Lock()
        self.device_id = str(uuid4())

    async def authenticate(self) -> Authentication:
        # Serialize refreshes so concurrent jobs share a valid token.
        async with self.authentication_lock:
            if self.authentication is not None:
                return self.authentication
            try:
                response = await self.http.post(
                    "/api/auth/sign_in",
                    data={
                        "login": self.settings.user.email,
                        "password": self.settings.user.password.get_secret_value(),
                    },
                )
                response.raise_for_status()
                self.authentication = Authentication.model_validate(response.json())
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 429 or error.response.status_code >= 500:
                    raise RetryablePunchError("Authentication temporarily unavailable") from None
                raise PermanentPunchError("Authentication rejected") from None
            except httpx.TransportError:
                raise RetryablePunchError("Authentication transport failure") from None
            except ValidationError, ValueError:
                raise PermanentPunchError("Invalid authentication response") from None
            return self.authentication

    async def register_punch(self, address: str, latitude: float, longitude: float) -> None:
        # Another job may invalidate the cached token while this job commits its
        # claim. Resolve a snapshot here instead of relying on mutable cache state.
        authentication = await self.authenticate()
        payload: PunchSubmission = {
            "_path": "/meu_ponto/registro_de_ponto",
            "_device": {
                "manufacturer": None,
                "model": None,
                "uuid": None,
                "version": None,
                "browser": {"name": "Firefox", "version": "67.0", "versionSearchString": "Firefox"},
            },
            "_appVersion": "0.10.32",
            "time_card": {
                "latitude": latitude,
                "longitude": longitude,
                "address": address,
                "reference_id": None,
                "original_latitude": latitude,
                "original_longitude": longitude,
                "original_address": address,
                "location_edited": True,
            },
        }
        try:
            response = await self.http.post(
                "/api/time_cards/register",
                json=payload,
                headers={
                    "uid": self.settings.user.email,
                    "uuid": self.device_id,
                    "token-type": "Bearer",
                    "access-token": authentication.token,
                    "client": authentication.client_id,
                    "expiry": authentication.expiry,
                    "Api-Version": "2",
                    "Origin": "https://app.pontomaisweb.com.br",
                    "Referer": "https://app.pontomaisweb.com.br/",
                },
            )
        except httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout:
            raise RetryablePunchError("Connection failed before submission") from None
        except httpx.TransportError:
            raise UncertainPunchError("Submission outcome is unknown after a transport failure") from None
        if response.status_code == 401:
            self.authentication = None
            raise RetryablePunchError("Authentication expired; refresh before retrying")
        if response.status_code == 429:
            raise RetryablePunchError("Remote rate limit reached")
        if response.status_code >= 500:
            raise UncertainPunchError("Server failed during submission")
        if not response.is_success:
            raise PermanentPunchError(f"Submission rejected with status {response.status_code}")
        try:
            PunchResponse.model_validate(response.json())
        except ValidationError, ValueError:
            raise UncertainPunchError("Submission returned no verifiable time card") from None
