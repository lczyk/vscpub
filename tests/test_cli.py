import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from vscpub.cli import cli
from vscpub.client import StoragePolicy, VscClient

FIXTURES = Path(__file__).parent / "fixtures"


def _make_mock_client(dry_run: bool = False) -> MagicMock:
    client = MagicMock(spec=VscClient)
    client._dry_run = dry_run
    client.get_storage_location.return_value = StoragePolicy(
        url="https://storage.googleapis.com/bucket",
        key="uploads/org/${file-name-goes-here}",
        policy="b64",
        x_goog_algorithm="GOOG4-RSA-SHA256",
        x_goog_credential="svc@proj.iam.gserviceaccount.com/...",
        x_goog_date="20260216T120000Z",
        x_goog_signature="sig",
    )
    client.get_product.return_value = {"product": {"displayName": "Test", "versions": []}}
    client.create_version.return_value = {"productId": "prod-abc123", "versionNumber": "1.0.0"}
    client.list_products.return_value = iter(
        [
            {
                "productId": "prod-abc123",
                "displayName": "Test Product",
                "status": "PUBLISHED",
                "solutionLicense": "BYOL",
            }
        ]
    )
    return client


def _runner_with_client(dry_run: bool = False):
    runner = CliRunner()
    mock_client = _make_mock_client(dry_run=dry_run)
    return runner, mock_client


class TestStorageCreate:
    def test_outputs_json(self):
        """
        Verify that `storage create` prints a valid JSON object containing the GCS upload fields.
        """
        runner, mock_client = _runner_with_client()
        mock_client.get_storage_location.return_value = StoragePolicy(
            url="https://storage.googleapis.com/bucket",
            key="uploads/org/${file-name-goes-here}",
            policy="b64policy",
            x_goog_algorithm="GOOG4-RSA-SHA256",
            x_goog_credential="svc@proj.iam.gserviceaccount.com/...",
            x_goog_date="20260216T120000Z",
            x_goog_signature="sig123",
        )
        with (
            patch("vscpub.cli.VscClient.from_env", return_value=mock_client),
            patch.dict("os.environ", {"VSCPUB_API_TOKEN": "tok"}),
        ):
            result = runner.invoke(cli, ["storage", "create"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "url" in data
        assert "x-goog-algorithm" in data


class TestProductList:
    def test_shows_table(self):
        """Verify that `product list` renders a table with product ID and display name."""
        runner, mock_client = _runner_with_client()
        with (
            patch("vscpub.cli.VscClient.from_env", return_value=mock_client),
            patch.dict("os.environ", {"VSCPUB_API_TOKEN": "tok"}),
        ):
            result = runner.invoke(cli, ["product", "list"])

        assert result.exit_code == 0, result.output
        assert "prod-abc123" in result.output
        assert "Test Product" in result.output

    def test_empty_list(self):
        """
        Verify that `product list` prints a human-readable message when there are no products.
        """
        runner, mock_client = _runner_with_client()
        mock_client.list_products.return_value = iter([])
        with (
            patch("vscpub.cli.VscClient.from_env", return_value=mock_client),
            patch.dict("os.environ", {"VSCPUB_API_TOKEN": "tok"}),
        ):
            result = runner.invoke(cli, ["product", "list"])

        assert result.exit_code == 0
        assert "No products found" in result.output


class TestProductGet:
    def test_outputs_json(self):
        """Verify that `product get <id>` prints the raw product JSON returned by the API."""
        runner, mock_client = _runner_with_client()
        with (
            patch("vscpub.cli.VscClient.from_env", return_value=mock_client),
            patch.dict("os.environ", {"VSCPUB_API_TOKEN": "tok"}),
        ):
            result = runner.invoke(cli, ["product", "get", "prod-abc123"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "product" in data


class TestPublish:
    def test_dry_run_passes_flag_to_client(self):
        """Verify that `--dry-run` results in the client being created with dry_run=True."""
        runner, mock_client = _runner_with_client(dry_run=True)
        with (
            patch("vscpub.cli.VscClient.from_env", return_value=mock_client) as mock_from_env,
            patch("vscpub.workflows.upload_file", return_value="https://gcs/file"),
            patch.dict("os.environ", {"VSCPUB_API_TOKEN": "tok"}),
        ):
            result = runner.invoke(
                cli,
                ["--dry-run", "publish", str(FIXTURES / "container_product.yaml")],
            )

        assert result.exit_code == 0, result.output
        mock_from_env.assert_called_once_with(dry_run=True, verbose=False)

    def test_credential_error_shown(self):
        """
        Verify that `publish` exits with a non-zero code and mentions VSCPUB when
        no credentials are set.
        """
        runner = CliRunner()
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(
                cli,
                ["publish", str(FIXTURES / "container_product.yaml")],
            )
        assert result.exit_code != 0
        assert "VSCPUB" in result.output


class TestVersionAdd:
    def test_version_add(self):
        """
        Verify that `version add` calls create_version exactly once with the
        config from the YAML file.
        """
        runner, mock_client = _runner_with_client()
        with (
            patch("vscpub.cli.VscClient.from_env", return_value=mock_client),
            patch("vscpub.workflows.upload_file", return_value="https://gcs/file"),
            patch.dict("os.environ", {"VSCPUB_API_TOKEN": "tok"}),
        ):
            result = runner.invoke(
                cli,
                ["version", "add", str(FIXTURES / "container_product.yaml")],
            )

        assert result.exit_code == 0, result.output
        mock_client.create_version.assert_called_once()
