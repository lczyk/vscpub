import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from vscpub.client import BASE_URL, StoragePolicy, VscClient
from vscpub.exceptions import ApiError, ConfigError


def _mock_response(status_code: int = 200, body: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.json.return_value = body or {}
    resp.text = json.dumps(body or {})
    return resp


def _make_client(dry_run: bool = False) -> VscClient:
    return VscClient(BASE_URL, "test-token", dry_run=dry_run)


class TestStoragePolicy:
    def test_round_trip(self):
        """
        Verify that StoragePolicy.from_dict followed by to_json_dict returns the
        original dict unchanged.
        """
        data = {
            "url": "https://storage.googleapis.com/bucket",
            "key": "uploads/org/${file-name-goes-here}",
            "policy": "base64policy",
            "x-goog-algorithm": "GOOG4-RSA-SHA256",
            "x-goog-credential": "svc@project.iam.gserviceaccount.com/...",
            "x-goog-date": "20260216T120000Z",
            "x-goog-signature": "abc123",
        }
        policy = StoragePolicy.from_dict(data)
        assert policy.to_json_dict() == data


class TestVscClientFromEnv:
    def test_no_credentials_raises(self):
        """Verify that from_env raises ConfigError when no credential env vars are set."""
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ConfigError, match="VSCPUB_CLIENT_ID"),
        ):
            VscClient.from_env()

    def test_both_credentials_raises(self):
        """
        Verify that from_env raises ConfigError when both API token and client
        credentials are provided.
        """
        env = {
            "VSCPUB_CLIENT_ID": "cid",
            "VSCPUB_CLIENT_SECRET": "csec",
            "VSCPUB_API_TOKEN": "tok",
        }
        with (
            patch.dict("os.environ", env, clear=True),
            pytest.raises(ConfigError, match="not both"),
        ):
            VscClient.from_env()

    def test_api_token_auth(self):
        """
        Verify that from_env exchanges VSCPUB_API_TOKEN for a JWT using the API_TOKEN grant type.
        """
        mock_resp = _mock_response(200, {"accessToken": "jwt-token"})
        with (
            patch.dict("os.environ", {"VSCPUB_API_TOKEN": "refresh-tok"}, clear=True),
            patch("requests.post", return_value=mock_resp) as mock_post,
        ):
            client = VscClient.from_env()
        mock_post.assert_called_once()
        call_body = mock_post.call_args.kwargs["json"]
        assert call_body["grantType"] == "API_TOKEN"
        assert call_body["apiToken"] == "refresh-tok"
        assert client._token == "jwt-token"

    def test_client_credentials_auth(self):
        """
        Verify that from_env uses the CLIENT_CREDENTIALS grant type when client
        ID and secret are set.
        """
        mock_resp = _mock_response(200, {"accessToken": "jwt-token"})
        env = {"VSCPUB_CLIENT_ID": "cid", "VSCPUB_CLIENT_SECRET": "csec"}
        with (
            patch.dict("os.environ", env, clear=True),
            patch("requests.post", return_value=mock_resp) as mock_post,
        ):
            VscClient.from_env()
        call_body = mock_post.call_args.kwargs["json"]
        assert call_body["grantType"] == "CLIENT_CREDENTIALS"


class TestVscClientMethods:
    def test_list_products_empty(self):
        """
        Verify that list_products returns an empty list and makes a single API
        call when no products exist.
        """
        client = _make_client()
        body = {"products": [], "totalCount": 0}
        mock_resp = _mock_response(200, body)
        client._session.get = MagicMock(return_value=mock_resp)

        result = list(client.list_products())
        assert result == []
        client._session.get.assert_called_once()

    def test_list_products_single_page(self):
        """
        Verify that list_products returns all products in a single-page response with one API call.
        """
        client = _make_client()
        products = [{"productId": "p1"}, {"productId": "p2"}]
        body = {"products": products, "totalCount": 2}
        mock_resp = _mock_response(200, body)
        client._session.get = MagicMock(return_value=mock_resp)

        result = list(client.list_products())
        assert result == products
        client._session.get.assert_called_once()

    def test_list_products_multi_page(self):
        """Verify that list_products transparently fetches all pages and merges the results."""
        client = _make_client()
        page1 = {"products": [{"productId": "p1"}], "totalCount": 2}
        page2 = {"products": [{"productId": "p2"}], "totalCount": 2}
        client._session.get = MagicMock(
            side_effect=[_mock_response(200, page1), _mock_response(200, page2)]
        )

        result = list(client.list_products(page_size=1))
        assert result == [{"productId": "p1"}, {"productId": "p2"}]
        assert client._session.get.call_count == 2

    def test_get_product(self):
        """Verify that get_product returns the full API response body for a given product ID."""
        client = _make_client()
        body = {"product": {"displayName": "Test"}}
        mock_resp = _mock_response(200, body)
        client._session.get = MagicMock(return_value=mock_resp)

        result = client.get_product("prod-123")
        assert result == body

    def test_update_product_sends_patch(self):
        """Verify that update_product issues exactly one PATCH request to the API."""
        client = _make_client()
        mock_resp = _mock_response(204)
        client._session.patch = MagicMock(return_value=mock_resp)

        client.update_product("prod-123", {"product": {"displayName": "New"}})
        client._session.patch.assert_called_once()

    def test_update_product_dry_run(self, capsys):
        """
        Verify that update_product in dry-run mode logs the skipped PATCH to
        stderr without calling the API.
        """
        client = _make_client(dry_run=True)
        client.update_product("prod-123", {"product": {"displayName": "New"}})
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.err
        assert "PATCH" in captured.err

    def test_update_version_sends_patch(self):
        """Verify that update_version issues exactly one PATCH request to the API."""
        client = _make_client()
        mock_resp = _mock_response(204)
        client._session.patch = MagicMock(return_value=mock_resp)

        payload = {"version": {"containerAssets": {"refresh": True}}}
        client.update_version("prod-123", "1.0.0", payload)
        client._session.patch.assert_called_once()
        url = client._session.patch.call_args.args[0]
        assert url.endswith("/products/prod-123/versions/1.0.0")

    def test_update_version_dry_run(self, capsys):
        """Verify that update_version in dry-run mode logs the skipped PATCH to stderr."""
        client = _make_client(dry_run=True)
        client.update_version("prod-123", "1.0.0", {"version": {}})
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.err
        assert "PATCH" in captured.err

    def test_create_version_dry_run(self, capsys):
        """
        Verify that create_version in dry-run mode logs the skipped POST and returns an empty dict.
        """
        client = _make_client(dry_run=True)
        result = client.create_version("prod-123", {"version": {}})
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.err
        assert result == {}

    def test_api_error_on_4xx(self):
        """Verify that a 4xx HTTP response raises ApiError with the correct status code."""
        client = _make_client()
        mock_resp = _mock_response(404, {"message": "Not found"})
        client._session.get = MagicMock(return_value=mock_resp)

        with pytest.raises(ApiError) as exc_info:
            client.get_product("nonexistent")
        assert exc_info.value.status_code == 404

    def test_get_storage_location(self):
        """
        Verify that get_storage_location unwraps the storageSpecs envelope and
        returns a populated StoragePolicy.
        """
        client = _make_client()
        # The real API wraps the policy fields under "storageSpecs", which is
        # not reflected in the spec but was confirmed from live responses.
        policy_fields = {
            "url": "https://storage.googleapis.com/bucket",
            "key": "uploads/org/${file-name-goes-here}",
            "policy": "b64",
            "x-goog-algorithm": "GOOG4-RSA-SHA256",
            "x-goog-credential": "svc@project.iam.gserviceaccount.com/20260216/auto/...",
            "x-goog-date": "20260216T120000Z",
            "x-goog-signature": "sig",
        }
        mock_resp = _mock_response(200, {"storageSpecs": policy_fields})
        client._session.get = MagicMock(return_value=mock_resp)

        policy = client.get_storage_location()
        assert isinstance(policy, StoragePolicy)
        assert policy.url == "https://storage.googleapis.com/bucket"
        assert policy.x_goog_algorithm == "GOOG4-RSA-SHA256"

    def test_list_products_empty_page_terminates(self):
        """
        Verify that list_products stops and does not loop forever when the API
        returns an empty products list while totalCount is still positive.
        """
        client = _make_client()
        # Simulates a malformed/race-condition response: totalCount says 5 but
        # the page is empty. The loop must break rather than spin indefinitely.
        body = {"products": [], "totalCount": 5}
        client._session.get = MagicMock(return_value=_mock_response(200, body))

        result = list(client.list_products())
        assert result == []
        client._session.get.assert_called_once()
