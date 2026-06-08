import dataclasses
from pathlib import Path
from typing import Any

import yaml

from vscpub.exceptions import ConfigError


@dataclasses.dataclass
class VmAssetConfig:
    # Local file path (Path) before upload; replaced with a GCS URL (str) by
    # _resolve_uploads() once the file has been pushed to cloud storage.
    file: Path | str
    hash_algo: str | None = None
    hash_digest: str | None = None


@dataclasses.dataclass
class ContainerAssetConfig:
    repository: str | None = None
    tag: str | None = None
    deployment_instructions: str | None = None
    # Local file path (Path) before upload; replaced with a GCS URL (str) by
    # _resolve_uploads() once the file has been pushed to cloud storage.
    file: Path | str | None = None
    refresh: bool = False


@dataclasses.dataclass
class EncryptionConfig:
    supports_encryption: bool
    types: list[str] = dataclasses.field(default_factory=list)
    supports_non_standard_encryption: bool = False
    others_description: str | None = None


@dataclasses.dataclass
class ExportConfig:
    eccn: str
    hts_applicable: bool
    eccn_other: str | None = None
    hts: str | None = None
    license_exception: str | None = None
    ccats_number: str | None = None
    # Local file path (Path) before upload; replaced with a GCS URL (str) by
    # _resolve_uploads() once the file has been pushed to cloud storage.
    ccats_document: Path | str | None = None


@dataclasses.dataclass
class EulaConfig:
    url: str | None = None
    text: str | None = None


@dataclasses.dataclass
class OpenSourceConfig:
    license_disclosure_url: str | None = None
    source_code_package_url: str | None = None


@dataclasses.dataclass
class ComplianceConfig:
    encryption: EncryptionConfig
    export: ExportConfig
    eula: EulaConfig
    open_source: OpenSourceConfig | None = None


@dataclasses.dataclass
class VersionConfig:
    version_number: str
    # release_tag and compliance are required when creating a version, but
    # optional for in-place updates (e.g. a container refresh) where only the
    # asset changes. See _parse_version(require_full=...).
    release_tag: str | None = None
    compliance: ComplianceConfig | None = None
    vm_asset: VmAssetConfig | None = None
    container_asset: ContainerAssetConfig | None = None


@dataclasses.dataclass
class MarketingConfig:
    overview: str | None = None
    description: str | None = None
    feature_highlights: list[str] = dataclasses.field(default_factory=list)
    # Local file paths (Path) before upload; replaced with GCS URL strings by
    # _resolve_product_uploads() once the files have been pushed to cloud storage.
    images: list[Path | str] = dataclasses.field(default_factory=list)
    videos: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ResourceConfig:
    name: str
    url: str


@dataclasses.dataclass
class SupportConfig:
    website: str | None = None
    emails: list[str] = dataclasses.field(default_factory=list)
    summary: str | None = None
    phones: list[str] = dataclasses.field(default_factory=list)
    resources: list[ResourceConfig] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class TechSpecsConfig:
    os_list: list[str] = dataclasses.field(default_factory=list)
    category: str | None = None
    vcf_components: list[str] = dataclasses.field(default_factory=list)
    technical_summary: str | None = None
    form_factor: str | None = None
    artifact_type: str | None = None


@dataclasses.dataclass
class SolutionConfig:
    product_id: str | None = None
    product_type: str = "DISTRIBUTABLE"
    display_name: str | None = None
    # Local file path (Path) before upload; replaced with a GCS URL (str) by
    # _resolve_product_uploads() once the file has been pushed to cloud storage.
    logo: Path | str | None = None
    license: str | None = None
    marketing: MarketingConfig | None = None
    support: SupportConfig | None = None
    tech_specs: TechSpecsConfig | None = None
    version: VersionConfig | None = None


def _resolve_path(base_dir: Path, value: str) -> Path:
    p = Path(value)
    if not p.is_absolute():
        p = base_dir / p
    return p


def _parse_encryption(data: dict[str, Any]) -> EncryptionConfig:
    if "supports_encryption" not in data:
        raise ConfigError("compliance.encryption.supports_encryption is required")
    return EncryptionConfig(
        supports_encryption=data["supports_encryption"],
        types=data.get("types", []),
        supports_non_standard_encryption=data.get("supports_non_standard_encryption", False),
        others_description=data.get("others_description"),
    )


def _parse_export(data: dict[str, Any], base_dir: Path) -> ExportConfig:
    if "eccn" not in data:
        raise ConfigError("compliance.export.eccn is required")
    if "hts_applicable" not in data:
        raise ConfigError("compliance.export.hts_applicable is required")
    ccats_doc = None
    if "ccats_document" in data:
        ccats_doc = _resolve_path(base_dir, data["ccats_document"])
    return ExportConfig(
        eccn=data["eccn"],
        hts_applicable=data["hts_applicable"],
        eccn_other=data.get("eccn_other"),
        hts=data.get("hts"),
        license_exception=data.get("license_exception"),
        ccats_number=data.get("ccats_number"),
        ccats_document=ccats_doc,
    )


def _parse_eula(data: dict[str, Any]) -> EulaConfig:
    has_url = "url" in data
    has_text = "text" in data
    if has_url and has_text:
        raise ConfigError("compliance.eula: url and text are mutually exclusive")
    if not has_url and not has_text:
        raise ConfigError("compliance.eula: either url or text is required")
    return EulaConfig(url=data.get("url"), text=data.get("text"))


def _parse_compliance(data: dict[str, Any], base_dir: Path) -> ComplianceConfig:
    if "encryption" not in data:
        raise ConfigError("compliance.encryption is required")
    if "export" not in data:
        raise ConfigError("compliance.export is required")
    if "eula" not in data:
        raise ConfigError("compliance.eula is required")

    open_source = None
    if "open_source" in data:
        os_data = data["open_source"]
        open_source = OpenSourceConfig(
            license_disclosure_url=os_data.get("license_disclosure_url"),
            source_code_package_url=os_data.get("source_code_package_url"),
        )

    return ComplianceConfig(
        encryption=_parse_encryption(data["encryption"]),
        export=_parse_export(data["export"], base_dir),
        eula=_parse_eula(data["eula"]),
        open_source=open_source,
    )


def _parse_version(
    data: dict[str, Any], base_dir: Path, *, require_full: bool = True
) -> VersionConfig:
    if "version_number" not in data:
        raise ConfigError("version.version_number is required")
    if require_full:
        if "release_tag" not in data:
            raise ConfigError("version.release_tag is required")
        if "compliance" not in data:
            raise ConfigError("version.compliance is required")

    has_vm = "vm_asset" in data
    has_container = "container_asset" in data
    if has_vm and has_container:
        raise ConfigError("version.vm_asset and version.container_asset are mutually exclusive")

    vm_asset = None
    if has_vm:
        va = data["vm_asset"]
        if "file" not in va:
            raise ConfigError("version.vm_asset.file is required")
        vm_asset = VmAssetConfig(
            file=_resolve_path(base_dir, va["file"]),
            hash_algo=va.get("hash_algo"),
            hash_digest=va.get("hash_digest"),
        )

    container_asset = None
    if has_container:
        ca = data["container_asset"]
        if not ca.get("refresh", False) and not (ca.get("repository") and ca.get("tag")):
            raise ConfigError(
                "version.container_asset: 'repository' and 'tag' are required "
                "unless 'refresh: true' is set"
            )
        file_path = None
        if "file" in ca:
            file_path = _resolve_path(base_dir, ca["file"])
        container_asset = ContainerAssetConfig(
            repository=ca.get("repository"),
            tag=ca.get("tag"),
            deployment_instructions=ca.get("deployment_instructions"),
            file=file_path,
            refresh=ca.get("refresh", False),
        )

    compliance = None
    if "compliance" in data:
        compliance = _parse_compliance(data["compliance"], base_dir)

    return VersionConfig(
        version_number=str(data["version_number"]),
        release_tag=data.get("release_tag"),
        compliance=compliance,
        vm_asset=vm_asset,
        container_asset=container_asset,
    )


def load_config(path: Path, *, require_full_version: bool = True) -> SolutionConfig:
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"Failed to parse YAML: {e}") from e

    if not isinstance(raw, dict) or "solution" not in raw:
        raise ConfigError("Config must have a top-level 'solution' key")

    data = raw["solution"]
    base_dir = path.parent

    logo = None
    if "logo" in data:
        logo = _resolve_path(base_dir, data["logo"])

    marketing = None
    if "marketing" in data:
        md = data["marketing"]
        images: list[Path | str] = [_resolve_path(base_dir, img) for img in md.get("images", [])]
        marketing = MarketingConfig(
            overview=md.get("overview"),
            description=md.get("description"),
            feature_highlights=md.get("feature_highlights", []),
            images=images,
            videos=md.get("videos", []),
        )

    support = None
    if "support" in data:
        sd = data["support"]
        resources = [ResourceConfig(name=r["name"], url=r["url"]) for r in sd.get("resources", [])]
        support = SupportConfig(
            website=sd.get("website"),
            emails=sd.get("emails", []),
            summary=sd.get("summary"),
            phones=sd.get("phones", []),
            resources=resources,
        )

    tech_specs = None
    if "tech_specs" in data:
        ts = data["tech_specs"]
        tech_specs = TechSpecsConfig(
            os_list=ts.get("os_list", []),
            category=ts.get("category"),
            vcf_components=ts.get("vcf_components", []),
            technical_summary=ts.get("technical_summary"),
            form_factor=ts.get("form_factor"),
            artifact_type=ts.get("artifact_type"),
        )

    version = None
    if "version" in data:
        version = _parse_version(data["version"], base_dir, require_full=require_full_version)

    return SolutionConfig(
        product_id=data.get("product_id"),
        product_type=data.get("product_type", "DISTRIBUTABLE"),
        display_name=data.get("display_name"),
        logo=logo,
        license=data.get("license"),
        marketing=marketing,
        support=support,
        tech_specs=tech_specs,
        version=version,
    )
