import hashlib
from unittest.mock import MagicMock, patch

import pytest
import requests

from vscpub.client import StoragePolicy
from vscpub.exceptions import ApiError, VscpubError
from vscpub.upload import upload_file, validate_hash


def _make_policy(key: str = "uploads/org/${file-name-goes-here}") -> StoragePolicy:
    return StoragePolicy(
        url="https://storage.googleapis.com/vsc-bucket",
        key=key,
        policy="b64policy",
        x_goog_algorithm="GOOG4-RSA-SHA256",
        x_goog_credential="svc@project.iam.gserviceaccount.com/20260216/auto/storage/...",
        x_goog_date="20260216T120000Z",
        x_goog_signature="sig123",
    )


class TestValidateHash:
    def test_matching_digest_passes(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        validate_hash(f, "SHA256", expected)  # must not raise

    def test_mismatched_digest_raises(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"hello world")
        with pytest.raises(VscpubError, match="Hash mismatch"):
            validate_hash(f, "SHA256", "deadbeef")

    def test_uppercase_digest_matches(self, tmp_path):
        """Uppercase hex digest from user config must match the lowercase hexdigest output."""
        f = tmp_path / "data.bin"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest().upper()
        validate_hash(f, "SHA256", expected)  # must not raise

    def test_unsupported_algo_raises(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"x")
        with pytest.raises(ValueError, match="Unsupported"):
            validate_hash(f, "MD5", "anything")


class TestUploadFile:
    def test_dry_run_returns_url(self, tmp_path, capsys):
        """
        Verify that upload_file in dry-run mode returns the expected GCS URL and
        logs a message to stderr without uploading.
        """
        f = tmp_path / "image.ova"
        f.write_bytes(b"fake ova")
        policy = _make_policy()

        url = upload_file(policy, f, dry_run=True)

        assert url == "https://storage.googleapis.com/vsc-bucket/uploads/org/image.ova"
        captured = capsys.readouterr()
        assert "[DRY RUN] UPLOAD" in captured.err
        assert "image.ova" in captured.err

    def test_filename_substituted_in_key(self, tmp_path, capsys):
        """
        Verify that the ${file-name-goes-here} placeholder in the storage key is
        replaced with the actual filename.
        """
        f = tmp_path / "logo.png"
        f.write_bytes(b"png")
        policy = _make_policy("uploads/org-123/${file-name-goes-here}")

        url = upload_file(policy, f, dry_run=True)
        assert url.endswith("/uploads/org-123/logo.png")

    def test_successful_upload(self, tmp_path):
        """
        Verify that upload_file sends the correct multipart POST to GCS and
        returns the final object URL.
        """
        f = tmp_path / "image.ova"
        f.write_bytes(b"fake ova")
        policy = _make_policy()

        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.ok = True
        mock_resp.status_code = 204

        with patch("requests.post", return_value=mock_resp) as mock_post:
            url = upload_file(policy, f)

        assert url == "https://storage.googleapis.com/vsc-bucket/uploads/org/image.ova"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.args[0] == policy.url
        fields = call_kwargs.kwargs["data"]
        assert fields["key"] == "uploads/org/image.ova"
        assert fields["policy"] == "b64policy"
        assert "x-goog-algorithm" in fields

    def test_upload_failure_raises(self, tmp_path):
        """
        Verify that upload_file raises ApiError with the HTTP status code when
        GCS returns a non-2xx response.
        """
        f = tmp_path / "image.ova"
        f.write_bytes(b"fake ova")
        policy = _make_policy()

        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.ok = False
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        with patch("requests.post", return_value=mock_resp), pytest.raises(ApiError) as exc_info:
            upload_file(policy, f)
        assert exc_info.value.status_code == 403

    def test_missing_placeholder_raises(self, tmp_path):
        """
        Verify that upload_file raises ValueError when the storage key has no filename placeholder.
        """
        f = tmp_path / "image.ova"
        f.write_bytes(b"fake ova")
        policy = _make_policy("uploads/org/fixed-key")

        with pytest.raises(ValueError, match="placeholder"):
            upload_file(policy, f, dry_run=True)
