import copy
import json
from pathlib import Path
from typing import Any

from vscpub.client import StoragePolicy, VscClient
from vscpub.config import (
    ComplianceConfig,
    ContainerAssetConfig,
    MarketingConfig,
    SolutionConfig,
    SupportConfig,
    TechSpecsConfig,
    VersionConfig,
    VmAssetConfig,
)
from vscpub.exceptions import VscpubError
from vscpub.upload import upload_file, validate_hash


def _ensure_storage(client: VscClient, policy: StoragePolicy | None) -> StoragePolicy:
    if policy is not None:
        return policy
    return client.get_storage_location()


def _upload_if_path(value: Path | str | None, policy: StoragePolicy, dry_run: bool) -> str | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return upload_file(policy, value, dry_run=dry_run)
    return value


def _resolve_product_uploads(
    config: SolutionConfig, policy: StoragePolicy, dry_run: bool
) -> SolutionConfig:
    """Upload product-level file assets (logo, marketing images) and return an updated config."""
    config = copy.deepcopy(config)

    config.logo = _upload_if_path(config.logo, policy, dry_run)

    if config.marketing is not None:
        config.marketing.images = [
            upload_file(policy, img, dry_run=dry_run) if isinstance(img, Path) else img
            for img in config.marketing.images
        ]

    return config


def _resolve_uploads(
    config: SolutionConfig, policy: StoragePolicy, dry_run: bool
) -> SolutionConfig:
    """Upload all file assets (product-level and version-level) and return an updated config."""
    config = _resolve_product_uploads(config, policy, dry_run)

    if config.version is None:
        return config

    va = config.version.vm_asset
    if va is not None and va.file is not None:
        assert isinstance(va.file, Path), "vm_asset.file must be a local Path before upload"
        if va.hash_algo is None or va.hash_digest is None:
            raise VscpubError(
                "vm_asset.hash_algo and vm_asset.hash_digest are both required"
                " when uploading a VM asset file"
            )
        validate_hash(va.file, va.hash_algo, va.hash_digest)
        va.file = upload_file(policy, va.file, dry_run=dry_run)

    ca = config.version.container_asset
    if ca is not None and ca.file is not None:
        assert isinstance(ca.file, Path), "container_asset.file must be a local Path before upload"
        ca.file = upload_file(policy, ca.file, dry_run=dry_run)

    exp = config.version.compliance.export
    if exp.ccats_document is not None:
        assert isinstance(exp.ccats_document, Path), (
            "ccats_document must be a local Path before upload"
        )
        exp.ccats_document = upload_file(policy, exp.ccats_document, dry_run=dry_run)

    return config


def _build_encryption_payload(enc: ComplianceConfig) -> dict[str, Any]:
    e = enc.encryption
    payload: dict[str, Any] = {"supportsEncryption": e.supports_encryption}
    if e.types:
        payload["encryptionTypes"] = e.types
    if e.supports_non_standard_encryption:
        payload["supportsNonStandardEncryption"] = e.supports_non_standard_encryption
    if e.others_description is not None:
        payload["othersDescription"] = e.others_description
    return payload


def _build_compliance_payload(compliance: ComplianceConfig) -> dict[str, Any]:
    exp = compliance.export
    eccn_details: dict[str, Any] = {"eccn": exp.eccn}
    if exp.eccn == "ECCN_OTHER" and exp.eccn_other is not None:
        eccn_details["other"] = exp.eccn_other

    hts_details: dict[str, Any] = {"htsApplicable": exp.hts_applicable}
    if exp.hts_applicable and exp.hts is not None:
        hts_details["hts"] = exp.hts

    export_payload: dict[str, Any] = {
        "eccnDetails": eccn_details,
        "htsDetails": hts_details,
    }
    if exp.license_exception is not None:
        export_payload["licenseException"] = exp.license_exception
    if exp.ccats_number is not None:
        export_payload["ccatsNumber"] = exp.ccats_number
    if exp.ccats_document is not None:
        export_payload["ccatsDocumentUrl"] = str(exp.ccats_document)

    eula: dict[str, Any] = {}
    if compliance.eula.url is not None:
        eula["url"] = compliance.eula.url
    else:
        eula["text"] = compliance.eula.text

    payload: dict[str, Any] = {
        "encryptionDetails": _build_encryption_payload(compliance),
        "exportCompliance": export_payload,
        "eulaDetails": eula,
    }

    if compliance.open_source is None:
        return payload

    os_payload: dict[str, Any] = {}
    if compliance.open_source.license_disclosure_url is not None:
        os_payload["licenseDisclosureUrl"] = compliance.open_source.license_disclosure_url
    if compliance.open_source.source_code_package_url is not None:
        os_payload["sourceCodePackageUrl"] = compliance.open_source.source_code_package_url
    if os_payload:
        payload["openSourceDisclosure"] = os_payload

    return payload


def _build_asset_details(version: VersionConfig) -> dict[str, Any]:
    if version.vm_asset is not None:
        va: VmAssetConfig = version.vm_asset
        asset: dict[str, Any] = {"assetURL": str(va.file)}
        if va.hash_digest is not None:
            asset["hashDigest"] = va.hash_digest
        if va.hash_algo is not None:
            asset["hashAlgo"] = va.hash_algo
        return {"vmAssets": asset}

    if version.container_asset is not None:
        ca: ContainerAssetConfig = version.container_asset
        if ca.refresh:
            return {"containerAssets": {"refresh": True}}
        container: dict[str, Any] = {}
        if ca.repository is not None:
            container["repositoryName"] = ca.repository
        if ca.tag is not None:
            container["imageTag"] = ca.tag
        if ca.file is not None:
            container["uploadURL"] = str(ca.file)
        if ca.deployment_instructions is not None:
            container["deploymentInstruction"] = ca.deployment_instructions
        return {"containerAssets": container}

    return {}


def _build_version_payload(version: VersionConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "versionNumber": version.version_number,
        "releaseTag": version.release_tag,
        "compliance": _build_compliance_payload(version.compliance),
    }
    payload.update(_build_asset_details(version))
    return payload


def _build_marketing_payload(marketing: MarketingConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if marketing.overview is not None:
        payload["overview"] = marketing.overview
    if marketing.description is not None:
        payload["description"] = marketing.description
    if marketing.feature_highlights:
        payload["featureHighlights"] = marketing.feature_highlights
    if marketing.images:
        payload["imageURLs"] = [str(img) for img in marketing.images]
    if marketing.videos:
        payload["videoURLs"] = marketing.videos
    return payload


def _build_support_payload(support: SupportConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if support.website is not None:
        payload["websiteURL"] = support.website
    if support.emails:
        payload["emailIds"] = support.emails
    if support.summary is not None:
        payload["summary"] = support.summary
    if support.phones:
        payload["phoneNumbers"] = support.phones
    if support.resources:
        payload["resources"] = [{"name": r.name, "url": r.url} for r in support.resources]
    return payload


def _build_tech_specs_payload(ts: TechSpecsConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if ts.os_list:
        payload["osList"] = ts.os_list
    if ts.category is not None:
        payload["category"] = ts.category
    if ts.vcf_components:
        payload["vcfComponents"] = ts.vcf_components
    if ts.technical_summary is not None:
        payload["technicalSummary"] = ts.technical_summary
    if ts.form_factor is not None:
        payload["formFactor"] = ts.form_factor
    if ts.artifact_type is not None:
        payload["artifactType"] = ts.artifact_type
    return payload


def _build_product_update_payload(config: SolutionConfig) -> dict[str, Any]:
    product: dict[str, Any] = {}
    if config.display_name is not None:
        product["displayName"] = config.display_name
    if config.logo is not None:
        product["logoURL"] = str(config.logo)
    if config.license is not None:
        product["license"] = config.license
    if config.marketing is not None:
        payload = _build_marketing_payload(config.marketing)
        if payload:
            product["marketingDetails"] = payload
    if config.support is not None:
        payload = _build_support_payload(config.support)
        if payload:
            product["supportDetails"] = payload
    if config.tech_specs is not None:
        payload = _build_tech_specs_payload(config.tech_specs)
        if payload:
            product["techSpecs"] = payload
    return {"product": product}


def _has_product_fields(config: SolutionConfig) -> bool:
    return any(
        [
            config.display_name is not None,
            config.logo is not None,
            config.license is not None,
            config.marketing is not None,
            config.support is not None,
            config.tech_specs is not None,
        ]
    )


def resolve_storage_policy(
    client: VscClient, storage_path: Path | None, dry_run: bool = False
) -> StoragePolicy | None:
    if storage_path is None:
        return None
    if storage_path.exists():
        try:
            return StoragePolicy.from_dict(json.loads(storage_path.read_text()))
        except (json.JSONDecodeError, KeyError) as e:
            raise VscpubError(f"Invalid storage policy file {storage_path}: {e}") from e
    policy = client.get_storage_location()
    if not dry_run:
        storage_path.write_text(json.dumps(policy.to_json_dict(), indent=2))
    return policy


def run_storage_create(client: VscClient) -> dict[str, str]:
    policy = client.get_storage_location()
    return policy.to_json_dict()


def run_product_update(
    client: VscClient,
    config: SolutionConfig,
    storage_policy: StoragePolicy | None,
    dry_run: bool,
) -> None:
    if config.product_id is None:
        raise VscpubError("solution.product_id is required for product update")
    if not _has_product_fields(config):
        raise VscpubError(
            "No product-level fields found in config (display_name, logo, license, "
            "marketing, support, tech_specs). Nothing to update."
        )

    product_id = config.product_id
    policy = _ensure_storage(client, storage_policy)
    config = _resolve_product_uploads(config, policy, dry_run)
    payload = _build_product_update_payload(config)
    client.update_product(product_id, payload)


def run_version_add(
    client: VscClient,
    config: SolutionConfig,
    storage_policy: StoragePolicy | None,
    dry_run: bool,
) -> dict[str, Any]:
    if config.product_id is None:
        raise VscpubError("solution.product_id is required for version add")
    if config.version is None:
        raise VscpubError("solution.version is required for version add")

    product_id = config.product_id
    policy = _ensure_storage(client, storage_policy)
    config = _resolve_uploads(config, policy, dry_run)
    assert config.version is not None
    payload: dict[str, Any] = {"version": _build_version_payload(config.version)}
    return client.create_version(product_id, payload)


def run_publish(
    client: VscClient,
    config: SolutionConfig,
    storage_policy: StoragePolicy | None,
    dry_run: bool,
) -> dict[str, Any]:
    if config.product_id is None:
        raise VscpubError("solution.product_id is required for publish")
    if config.version is None:
        raise VscpubError("solution.version is required for publish")

    product_id = config.product_id
    product = client.get_product(product_id)
    existing_versions = {
        v["versionNumber"] for v in product.get("product", {}).get("versions", [])
    }
    if config.version.version_number in existing_versions:
        raise VscpubError(
            f"Version {config.version.version_number} already exists on product "
            f"{product_id}. Use 'version add' only if you intend to add it explicitly."
        )

    policy = _ensure_storage(client, storage_policy)
    config = _resolve_uploads(config, policy, dry_run)

    if _has_product_fields(config):
        payload = _build_product_update_payload(config)
        client.update_product(product_id, payload)

    assert config.version is not None
    version_payload: dict[str, Any] = {"version": _build_version_payload(config.version)}
    return client.create_version(product_id, version_payload)
