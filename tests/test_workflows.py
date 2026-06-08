from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vscpub.client import StoragePolicy, VscClient
from vscpub.config import ComplianceConfig, load_config
from vscpub.exceptions import VscpubError
from vscpub.workflows import (
    _build_compliance_payload,
    _build_version_payload,
    run_product_create,
    run_product_update,
    run_publish,
    run_version_add,
    run_version_update,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _make_client() -> VscClient:
    client = MagicMock(spec=VscClient)
    client.get_storage_location.return_value = StoragePolicy(
        url="https://storage.googleapis.com/bucket",
        key="uploads/org/${file-name-goes-here}",
        policy="b64",
        x_goog_algorithm="GOOG4-RSA-SHA256",
        x_goog_credential="svc@proj.iam.gserviceaccount.com/...",
        x_goog_date="20260216T120000Z",
        x_goog_signature="sig",
    )
    client.get_product.return_value = {"product": {"versions": []}}
    client.create_version.return_value = {"productId": "prod-abc123", "versionNumber": "1.0.0"}
    return client


def _make_policy() -> StoragePolicy:
    return StoragePolicy(
        url="https://storage.googleapis.com/bucket",
        key="uploads/org/${file-name-goes-here}",
        policy="b64",
        x_goog_algorithm="GOOG4-RSA-SHA256",
        x_goog_credential="svc@proj.iam.gserviceaccount.com/...",
        x_goog_date="20260216T120000Z",
        x_goog_signature="sig",
    )


class TestBuildCompliancePayload:
    def _make_compliance(self, eccn: str, eccn_other: str | None = None) -> ComplianceConfig:
        """Build a minimal ComplianceConfig for testing ECCN payload construction."""
        from vscpub.config import EncryptionConfig, EulaConfig, ExportConfig

        return ComplianceConfig(
            encryption=EncryptionConfig(supports_encryption=False),
            export=ExportConfig(eccn=eccn, hts_applicable=False, eccn_other=eccn_other),
            eula=EulaConfig(text="terms"),
        )

    def test_eccn_other_includes_other_field(self):
        """
        Verify that the 'other' field is included in the payload when eccn is
        ECCN_OTHER and eccn_other is set.
        """
        compliance = self._make_compliance("ECCN_OTHER", eccn_other="Not Subject to EAR")
        payload = _build_compliance_payload(compliance)
        eccn_details = payload["exportCompliance"]["eccnDetails"]
        assert eccn_details["eccn"] == "ECCN_OTHER"
        assert eccn_details["other"] == "Not Subject to EAR"

    def test_eccn_other_without_description_omits_other_field(self):
        """
        Verify that the 'other' field is omitted when eccn is ECCN_OTHER but no
        eccn_other description is given.
        """
        compliance = self._make_compliance("ECCN_OTHER", eccn_other=None)
        payload = _build_compliance_payload(compliance)
        eccn_details = payload["exportCompliance"]["eccnDetails"]
        assert "other" not in eccn_details

    def test_non_eccn_other_omits_other_field(self):
        """
        Verify that the 'other' field is omitted for standard ECCN values that
        do not require a free-text description.
        """
        compliance = self._make_compliance("ECCN_EAR99")
        payload = _build_compliance_payload(compliance)
        eccn_details = payload["exportCompliance"]["eccnDetails"]
        assert eccn_details["eccn"] == "ECCN_EAR99"
        assert "other" not in eccn_details


class TestBuildVersionPayload:
    def test_vm_payload(self):
        """
        Verify that a VM product config produces a version payload with the
        correct OVA asset URL and compliance fields.
        """
        cfg = load_config(FIXTURES / "vm_product.yaml")
        assert cfg.version is not None
        cfg.version.vm_asset.file = "https://storage.googleapis.com/bucket/image.ova"  # type: ignore[union-attr]
        payload = _build_version_payload(cfg.version)

        assert payload["versionNumber"] == "1.0.0"
        assert payload["releaseTag"] == "GENERAL_AVAILABILITY"
        assert "assetURL" in payload["vmAssets"]
        assert payload["compliance"]["encryptionDetails"]["supportsEncryption"] is True

    def test_container_payload(self):
        """
        Verify that a container product config produces a version payload with
        the correct repository name and image tag.
        """
        cfg = load_config(FIXTURES / "container_product.yaml")
        assert cfg.version is not None
        payload = _build_version_payload(cfg.version)

        assert payload["versionNumber"] == "2.1.0"
        assert "containerAssets" in payload
        ca = payload["containerAssets"]
        assert ca["repositoryName"] == "bitnami/nginx"
        assert ca["imageTag"] == "2.1.0"


class TestRunPublish:
    def test_raises_without_product_id(self):
        """Verify that run_publish raises VscpubError when the config has no product_id."""
        cfg = load_config(FIXTURES / "vm_product.yaml")
        cfg.product_id = None
        client = _make_client()
        with pytest.raises(VscpubError, match="product_id"):
            run_publish(client, cfg, None, dry_run=True)

    def test_raises_on_duplicate_version(self):
        """
        Verify that run_publish raises VscpubError when the target version
        already exists on the product.
        """
        cfg = load_config(FIXTURES / "vm_product.yaml")
        client = _make_client()
        client.get_product.return_value = {"product": {"versions": [{"versionNumber": "1.0.0"}]}}
        with pytest.raises(VscpubError, match="already exists"):
            run_publish(client, cfg, _make_policy(), dry_run=True)

    def test_calls_update_product_when_product_fields_present(self):
        """
        Verify that run_publish calls both update_product and create_version
        when product-level fields are set.
        """
        cfg = load_config(FIXTURES / "vm_product.yaml")
        assert cfg.version is not None and cfg.version.vm_asset is not None
        cfg.version.vm_asset.hash_algo = "SHA256"
        cfg.version.vm_asset.hash_digest = "abc123"
        client = _make_client()

        with (
            patch("vscpub.workflows.upload_file", return_value="https://gcs/file"),
            patch("vscpub.workflows.validate_hash"),
        ):
            run_publish(client, cfg, _make_policy(), dry_run=False)

        client.update_product.assert_called_once()
        client.create_version.assert_called_once()

    def test_skips_update_product_when_no_product_fields(self):
        """
        Verify that run_publish skips update_product and only calls create_version
        when no product-level fields are set.
        """
        cfg = load_config(FIXTURES / "container_product.yaml")
        cfg.display_name = None
        cfg.logo = None
        cfg.license = None
        cfg.marketing = None
        cfg.support = None
        cfg.tech_specs = None
        client = _make_client()

        run_publish(client, cfg, _make_policy(), dry_run=True)

        client.update_product.assert_not_called()
        client.create_version.assert_called_once()


class TestHashValidation:
    def test_valid_hash_allows_upload(self, tmp_path):
        """Verify that run_version_add proceeds when hash_digest matches the file content."""
        cfg = load_config(FIXTURES / "vm_product.yaml")
        assert cfg.version is not None and cfg.version.vm_asset is not None
        f = tmp_path / "database-v1.0.0.ova"
        f.write_bytes(b"ova content")
        import hashlib

        cfg.version.vm_asset.file = f
        cfg.version.vm_asset.hash_algo = "SHA256"
        cfg.version.vm_asset.hash_digest = hashlib.sha256(b"ova content").hexdigest()
        client = _make_client()

        with patch("vscpub.workflows.upload_file", return_value="https://gcs/file"):
            run_version_add(client, cfg, _make_policy(), dry_run=False)

        client.create_version.assert_called_once()

    def test_hash_mismatch_raises_before_upload(self, tmp_path):
        """
        Verify that run_version_add raises VscpubError and never calls upload
        when the digest is wrong.
        """
        cfg = load_config(FIXTURES / "vm_product.yaml")
        assert cfg.version is not None and cfg.version.vm_asset is not None
        cfg.logo = None
        cfg.marketing = None
        f = tmp_path / "database-v1.0.0.ova"
        f.write_bytes(b"ova content")
        cfg.version.vm_asset.file = f
        cfg.version.vm_asset.hash_algo = "SHA256"
        cfg.version.vm_asset.hash_digest = "deadbeef"
        client = _make_client()

        with (
            patch("vscpub.workflows.upload_file") as mock_upload,
            pytest.raises(VscpubError, match="Hash mismatch"),
        ):
            run_version_add(client, cfg, _make_policy(), dry_run=False)

        mock_upload.assert_not_called()


class TestRunVersionAdd:
    def test_raises_without_version(self):
        """Verify that run_version_add raises VscpubError when the config has no version block."""
        cfg = load_config(FIXTURES / "vm_product.yaml")
        cfg.version = None
        client = _make_client()
        with pytest.raises(VscpubError, match="version"):
            run_version_add(client, cfg, _make_policy(), dry_run=True)

    def test_creates_version(self):
        """
        Verify that run_version_add calls create_version exactly once with the
        parsed version config.
        """
        cfg = load_config(FIXTURES / "container_product.yaml")
        client = _make_client()

        run_version_add(client, cfg, _make_policy(), dry_run=True)
        client.create_version.assert_called_once()


class TestRunProductCreate:
    def test_creates_product(self):
        """
        Verify run_product_create POSTs a full product payload (with productType,
        solutionLicense, and an initial version) and returns the new productId.
        """
        cfg = load_config(FIXTURES / "vm_product.yaml")
        assert cfg.version is not None and cfg.version.vm_asset is not None
        cfg.version.vm_asset.hash_algo = "SHA256"
        cfg.version.vm_asset.hash_digest = "abc123"
        client = _make_client()
        client.create_product.return_value = {"productId": "new-id"}

        with (
            patch("vscpub.workflows.upload_file", return_value="https://gcs/file"),
            patch("vscpub.workflows.validate_hash"),
        ):
            result = run_product_create(client, cfg, _make_policy(), dry_run=False)

        client.create_product.assert_called_once()
        payload = client.create_product.call_args.args[0]
        assert payload["product"]["displayName"] == "Enterprise Database Solution"
        assert payload["product"]["solutionLicense"] == "BYOL"
        assert payload["product"]["productType"] == "DISTRIBUTABLE"
        assert "version" in payload["product"]
        assert result == {"productId": "new-id"}

    def test_raises_on_missing_fields(self):
        """Verify run_product_create rejects a config missing a required section."""
        cfg = load_config(FIXTURES / "vm_product.yaml")
        cfg.support = None
        client = _make_client()
        with pytest.raises(VscpubError, match="support"):
            run_product_create(client, cfg, _make_policy(), dry_run=True)


class TestRunVersionUpdate:
    def _refresh_config(self, tmp_path):
        f = tmp_path / "refresh.yaml"
        f.write_text(
            """
solution:
  product_id: prod-rust
  version:
    version_number: "1.75-24.04_stable"
    container_asset:
      refresh: true
"""
        )
        return load_config(f, require_full_version=False)

    def test_refresh_patches_version_without_storage(self, tmp_path):
        """
        A refresh sends a containerAssets.refresh PATCH to update_version and must
        not request a storage location (no asset to upload).
        """
        cfg = self._refresh_config(tmp_path)
        client = _make_client()

        run_version_update(client, cfg, None, dry_run=False)

        client.get_storage_location.assert_not_called()
        client.update_version.assert_called_once()
        args = client.update_version.call_args.args
        assert args[0] == "prod-rust"
        assert args[1] == "1.75-24.04_stable"
        payload = args[2]
        assert payload["version"]["containerAssets"] == {"refresh": True}
        assert "versionNumber" not in payload["version"]
        assert "compliance" not in payload["version"]

    def test_raises_without_product_id(self, tmp_path):
        """Verify run_version_update rejects a config with no product_id."""
        cfg = self._refresh_config(tmp_path)
        cfg.product_id = None
        client = _make_client()
        with pytest.raises(VscpubError, match="product_id"):
            run_version_update(client, cfg, None, dry_run=True)


class TestRunProductUpdate:
    def test_raises_without_product_id(self):
        """Verify that run_product_update raises VscpubError when the config has no product_id."""
        cfg = load_config(FIXTURES / "vm_product.yaml")
        cfg.product_id = None
        client = _make_client()
        with pytest.raises(VscpubError, match="product_id"):
            run_product_update(client, cfg, None, dry_run=True)

    def test_patches_product(self):
        """
        Verify that run_product_update calls update_product with the display name from the config.
        """
        cfg = load_config(FIXTURES / "vm_product.yaml")
        cfg.version = None
        client = _make_client()

        with patch("vscpub.workflows.upload_file", return_value="https://gcs/logo.png"):
            run_product_update(client, cfg, _make_policy(), dry_run=False)

        client.update_product.assert_called_once()
        payload = client.update_product.call_args.args[1]
        assert payload["product"]["displayName"] == "Enterprise Database Solution"

    def test_does_not_upload_version_assets(self):
        """product update must not touch version file assets even when version is present."""
        cfg = load_config(FIXTURES / "vm_product.yaml")
        client = _make_client()

        with patch("vscpub.workflows.upload_file", return_value="https://gcs/file") as mock_upload:
            run_product_update(client, cfg, _make_policy(), dry_run=False)

        uploaded_paths = [call.args[1] for call in mock_upload.call_args_list]
        assert not any(str(p).endswith(".ova") for p in uploaded_paths)

    def test_raises_when_no_product_fields(self):
        """
        Verify that run_product_update raises VscpubError when the config has a
        product_id but no product-level fields to send, rather than silently doing nothing.
        """
        cfg = load_config(FIXTURES / "vm_product.yaml")
        cfg.display_name = None
        cfg.logo = None
        cfg.license = None
        cfg.marketing = None
        cfg.support = None
        cfg.tech_specs = None
        client = _make_client()

        with pytest.raises(VscpubError, match="Nothing to update"):
            run_product_update(client, cfg, _make_policy(), dry_run=False)

        client.update_product.assert_not_called()
