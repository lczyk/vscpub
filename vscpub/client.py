from __future__ import annotations

import dataclasses
import json
import os
import sys
from collections.abc import Iterator
from typing import Any, cast

import requests

from vscpub.exceptions import ApiError, ConfigError

BASE_URL = "https://eapi.broadcom.com/vcf/vsc/gtw/api/v3"


@dataclasses.dataclass
class StoragePolicy:
    url: str
    key: str
    policy: str
    x_goog_algorithm: str
    x_goog_credential: str
    x_goog_date: str
    x_goog_signature: str

    def to_json_dict(self) -> dict[str, str]:
        return {
            "url": self.url,
            "key": self.key,
            "policy": self.policy,
            "x-goog-algorithm": self.x_goog_algorithm,
            "x-goog-credential": self.x_goog_credential,
            "x-goog-date": self.x_goog_date,
            "x-goog-signature": self.x_goog_signature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> StoragePolicy:
        return cls(
            url=data["url"],
            key=data["key"],
            policy=data["policy"],
            x_goog_algorithm=data["x-goog-algorithm"],
            x_goog_credential=data["x-goog-credential"],
            x_goog_date=data["x-goog-date"],
            x_goog_signature=data["x-goog-signature"],
        )


class _Session(requests.Session):
    def request(self, *args: Any, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", 30)
        return super().request(*args, **kwargs)


def _raise_for_status(response: requests.Response) -> None:
    if not response.ok:
        try:
            msg = response.json().get("message", response.text)
        except Exception:
            msg = response.text
        raise ApiError(response.status_code, msg)


class VscClient:
    def __init__(
        self, base_url: str, token: str, dry_run: bool = False, verbose: bool = False
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._dry_run = dry_run
        self._session = _Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})
        if verbose:
            self._session.hooks["response"].append(
                lambda r, *a, **kw: print(f"{r.request.method} {r.request.url}", file=sys.stderr)
            )

    @classmethod
    def from_env(cls, dry_run: bool = False, verbose: bool = False) -> VscClient:
        client_id = os.environ.get("VSCPUB_CLIENT_ID")
        client_secret = os.environ.get("VSCPUB_CLIENT_SECRET")
        api_token = os.environ.get("VSCPUB_API_TOKEN")

        has_oauth = bool(client_id and client_secret)
        has_token = bool(api_token)

        if has_oauth and has_token:
            raise ConfigError(
                "Set either VSCPUB_CLIENT_ID+VSCPUB_CLIENT_SECRET or VSCPUB_API_TOKEN, not both"
            )
        if not has_oauth and not has_token:
            raise ConfigError("Set VSCPUB_CLIENT_ID+VSCPUB_CLIENT_SECRET or VSCPUB_API_TOKEN")

        body: dict[str, Any]
        if has_oauth:
            assert client_id is not None and client_secret is not None
            body = {
                "grantType": "CLIENT_CREDENTIALS",
                "credentials": {"clientId": client_id, "clientSecret": client_secret},
            }
        else:
            body = {"grantType": "API_TOKEN", "apiToken": api_token}

        resp = requests.post(f"{BASE_URL}/auth", json=body, timeout=30)
        _raise_for_status(resp)
        token: str = resp.json()["accessToken"]
        return cls(BASE_URL, token, dry_run=dry_run, verbose=verbose)

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    def _dry_run_mutate(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        print(
            f"[DRY RUN] {method} {self._url(path)}\n{json.dumps(payload, indent=2)}",
            file=sys.stderr,
        )
        return {}

    def list_products(self, page_size: int = 50) -> Iterator[dict[str, Any]]:
        offset = 0
        while True:
            resp = self._session.get(
                self._url("/products"), params={"limit": page_size, "offset": offset}
            )
            _raise_for_status(resp)
            data: dict[str, Any] = resp.json()
            products: list[dict[str, Any]] = data.get("products", [])
            if not products:
                break
            yield from products
            offset += len(products)
            if offset >= data.get("totalCount", 0):
                break

    def get_product(self, product_id: str) -> dict[str, Any]:
        resp = self._session.get(self._url(f"/products/{product_id}"))
        _raise_for_status(resp)
        return cast(dict[str, Any], resp.json())

    def create_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._dry_run:
            return self._dry_run_mutate("POST", "/products", payload)
        resp = self._session.post(self._url("/products"), json=payload)
        _raise_for_status(resp)
        return cast(dict[str, Any], resp.json())

    def update_product(self, product_id: str, payload: dict[str, Any]) -> None:
        if self._dry_run:
            self._dry_run_mutate("PATCH", f"/products/{product_id}", payload)
            return
        resp = self._session.patch(self._url(f"/products/{product_id}"), json=payload)
        _raise_for_status(resp)

    def create_version(self, product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._dry_run:
            return self._dry_run_mutate("POST", f"/products/{product_id}/versions", payload)
        resp = self._session.post(self._url(f"/products/{product_id}/versions"), json=payload)
        _raise_for_status(resp)
        return cast(dict[str, Any], resp.json())

    def update_version(
        self, product_id: str, version_number: str, payload: dict[str, Any]
    ) -> None:
        # NOTE: the OpenAPI spec spells this path singular (/version/{ver}), but the
        # rest of this client uses the plural /versions form (create/get); kept
        # consistent here. Returns 204 No Content, so there is no body to parse.
        path = f"/products/{product_id}/versions/{version_number}"
        if self._dry_run:
            self._dry_run_mutate("PATCH", path, payload)
            return
        resp = self._session.patch(self._url(path), json=payload)
        _raise_for_status(resp)

    def get_product_version(self, product_id: str, version_number: str) -> dict[str, Any]:
        resp = self._session.get(self._url(f"/products/{product_id}/versions/{version_number}"))
        _raise_for_status(resp)
        return cast(dict[str, Any], resp.json())

    def get_storage_location(self) -> StoragePolicy:
        resp = self._session.get(self._url("/storage-location"))
        _raise_for_status(resp)
        data: dict[str, Any] = resp.json()
        return StoragePolicy.from_dict(data["storageSpecs"])
