import hashlib
import sys
from pathlib import Path

import requests

from vscpub.client import StoragePolicy
from vscpub.exceptions import ApiError, VscpubError

_HASH_ALGOS = {
    "SHA1": hashlib.sha1,
    "SHA256": hashlib.sha256,
    "SHA512": hashlib.sha512,
}

_CHUNK_SIZE = 65536


def _compute_hash(path: Path, algo: str) -> str:
    factory = _HASH_ALGOS.get(algo.upper())
    if factory is None:
        raise ValueError(f"Unsupported hash algorithm: {algo}")
    h = factory()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def validate_hash(path: Path, algo: str, expected: str) -> None:
    actual = _compute_hash(path, algo)
    if actual != expected.lower():
        raise VscpubError(f"Hash mismatch for {path.name}: expected {expected}, got {actual}")


_KEY_PLACEHOLDER = "${file-name-goes-here}"


def upload_file(policy: StoragePolicy, local_path: Path, dry_run: bool = False) -> str:
    if _KEY_PLACEHOLDER not in policy.key:
        raise ValueError(
            f"Storage key template is missing the '{_KEY_PLACEHOLDER}' placeholder: {policy.key!r}"
        )
    final_key = policy.key.replace(_KEY_PLACEHOLDER, local_path.name)
    gcs_url = f"{policy.url.rstrip('/')}/{final_key}"

    if dry_run:
        print(f"[DRY RUN] UPLOAD {local_path} → {gcs_url}", file=sys.stderr)
        return gcs_url

    with local_path.open("rb") as f:
        fields = {
            "key": final_key,
            "policy": policy.policy,
            "x-goog-algorithm": policy.x_goog_algorithm,
            "x-goog-credential": policy.x_goog_credential,
            "x-goog-date": policy.x_goog_date,
            "x-goog-signature": policy.x_goog_signature,
        }
        resp = requests.post(policy.url, data=fields, files={"file": f}, timeout=300)

    if not resp.ok:
        raise ApiError(resp.status_code, f"GCS upload failed: {resp.text}")

    return gcs_url
