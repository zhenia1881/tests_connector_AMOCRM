from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AmoCRMError(RuntimeError):
    """Raised when amoCRM returns an error response."""


@dataclass
class AmoCRMToken:
    access_token: str
    refresh_token: str
    expires_at: float

    @property
    def is_expired(self) -> bool:
        return time() >= self.expires_at - 30


class Response:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._payload or {}


class SimpleHTTPSession:
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        json: Any = None,
        params: dict[str, Any] | None = None,
        timeout: int = 10,
    ) -> Response:
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"

        body: bytes | None = None
        if json is not None:
            body = __import__("json").dumps(json).encode("utf-8")

        request = Request(url=url, data=body, headers=headers or {}, method=method)

        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("utf-8")
                data = __import__("json").loads(payload) if payload else {}
                return Response(response.status, data, payload)
        except HTTPError as error:
            text = error.read().decode("utf-8")
            return Response(error.code, text=text)
        except URLError as error:
            raise AmoCRMError(f"Network error: {error}") from error

    def post(self, url: str, json: Any, timeout: int = 10) -> Response:
        return self.request("POST", url, headers={"Content-Type": "application/json"}, json=json, timeout=timeout)


class AmoCRMConnector:
    """Minimal amoCRM API connector with automatic token refresh."""

    def __init__(
        self,
        base_domain: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token: AmoCRMToken,
        session: Any | None = None,
    ) -> None:
        self.base_url = f"https://{base_domain}.amocrm.ru/api/v4"
        self.token_url = f"https://{base_domain}.amocrm.ru/oauth2/access_token"
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token = token
        self.session = session or SimpleHTTPSession()

    def refresh_access_token(self) -> None:
        response = self.session.post(
            self.token_url,
            json={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.token.refresh_token,
                "redirect_uri": self.redirect_uri,
            },
            timeout=10,
        )
        if response.status_code != 200:
            raise AmoCRMError(f"Failed to refresh token: {response.status_code} {response.text}")

        payload = response.json()
        self.token = AmoCRMToken(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token", self.token.refresh_token),
            expires_at=time() + payload.get("expires_in", 900),
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if self.token.is_expired:
            self.refresh_access_token()

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token.access_token}"
        headers["Content-Type"] = "application/json"

        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            timeout=10,
            **kwargs,
        )
        if response.status_code >= 400:
            raise AmoCRMError(f"amoCRM API error: {response.status_code} {response.text}")

        if response.status_code == 204:
            return {}
        return response.json()

    def get_leads(self, limit: int = 50, page: int = 1) -> list[dict[str, Any]]:
        data = self._request("GET", "/leads", params={"limit": limit, "page": page})
        return data.get("_embedded", {}).get("leads", [])

    def create_contact(self, name: str) -> dict[str, Any]:
        payload = [{"name": name}]
        data = self._request("POST", "/contacts", json=payload)
        contacts = data.get("_embedded", {}).get("contacts", [])
        if not contacts:
            raise AmoCRMError("Contact creation returned empty payload")
        return contacts[0]
