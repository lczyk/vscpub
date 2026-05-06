from pathlib import Path

import pytest

from vscpub.config import load_config
from vscpub.exceptions import ConfigError

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_vm_product():
    cfg = load_config(FIXTURES / "vm_product.yaml")
    assert cfg.product_id == "prod-abc123"
    assert cfg.display_name == "Enterprise Database Solution"
    assert cfg.license == "BYOL"
    assert cfg.logo == FIXTURES / "logo.png"

    assert cfg.marketing is not None
    assert cfg.marketing.overview == "High-performance database solution for VCF environments"
    assert len(cfg.marketing.feature_highlights) == 2
    assert cfg.marketing.images == [FIXTURES / "screenshot1.png"]

    assert cfg.support is not None
    assert cfg.support.website == "https://www.example.com/support"
    assert cfg.support.emails == ["support@example.com"]
    assert len(cfg.support.resources) == 1

    assert cfg.tech_specs is not None
    assert cfg.tech_specs.category == "DATABASES"
    assert "VSPHERE" in cfg.tech_specs.vcf_components

    assert cfg.version is not None
    assert cfg.version.version_number == "1.0.0"
    assert cfg.version.release_tag == "GENERAL_AVAILABILITY"
    assert cfg.version.vm_asset is not None
    assert cfg.version.vm_asset.file == FIXTURES / "database-v1.0.0.ova"
    assert cfg.version.container_asset is None

    enc = cfg.version.compliance.encryption
    assert enc.supports_encryption is True
    assert "USER_AUTHENTICATION" in enc.types

    exp = cfg.version.compliance.export
    assert exp.eccn == "ECCN_5D992c"
    assert exp.hts_applicable is True
    assert exp.hts == "8523.49.20.00"

    assert cfg.version.compliance.eula.url == "https://example.com/eula.pdf"
    assert cfg.version.compliance.eula.text is None


def test_load_container_product():
    cfg = load_config(FIXTURES / "container_product.yaml")
    assert cfg.product_id == "prod-xyz789"
    assert cfg.logo is None

    assert cfg.version is not None
    assert cfg.version.vm_asset is None
    ca = cfg.version.container_asset
    assert ca is not None
    assert ca.repository == "bitnami/nginx"
    assert ca.tag == "2.1.0"
    assert ca.refresh is False

    assert cfg.version.compliance.eula.text is not None
    assert cfg.version.compliance.eula.url is None


def test_eccn_other_parsed(tmp_path):
    f = tmp_path / "cfg.yaml"
    f.write_text(
        """
solution:
  version:
    version_number: "1.0.0"
    release_tag: "GENERAL_AVAILABILITY"
    compliance:
      encryption:
        supports_encryption: false
      export:
        eccn: "ECCN_OTHER"
        eccn_other: "Not Subject to EAR"
        hts_applicable: false
        license_exception: "NLR"
      eula:
        text: "terms"
"""
    )
    cfg = load_config(f)
    exp = cfg.version.compliance.export
    assert exp.eccn == "ECCN_OTHER"
    assert exp.eccn_other == "Not Subject to EAR"


def test_missing_solution_key(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("foo: bar\n")
    with pytest.raises(ConfigError, match="top-level 'solution'"):
        load_config(f)


def test_vm_and_container_mutually_exclusive(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(
        """
solution:
  version:
    version_number: "1.0.0"
    release_tag: "GENERAL_AVAILABILITY"
    vm_asset:
      file: "image.ova"
    container_asset:
      repository: "nginx"
      tag: "latest"
    compliance:
      encryption:
        supports_encryption: false
      export:
        eccn: "ECCN_EAR99"
        hts_applicable: false
        license_exception: "NLR"
      eula:
        text: "text"
"""
    )
    with pytest.raises(ConfigError, match="mutually exclusive"):
        load_config(f)


def test_eula_url_and_text_mutually_exclusive(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(
        """
solution:
  version:
    version_number: "1.0.0"
    release_tag: "GENERAL_AVAILABILITY"
    compliance:
      encryption:
        supports_encryption: false
      export:
        eccn: "ECCN_EAR99"
        hts_applicable: false
        license_exception: "NLR"
      eula:
        url: "https://example.com/eula"
        text: "also text"
"""
    )
    with pytest.raises(ConfigError, match="mutually exclusive"):
        load_config(f)


def test_eula_requires_one_field(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(
        """
solution:
  version:
    version_number: "1.0.0"
    release_tag: "GENERAL_AVAILABILITY"
    compliance:
      encryption:
        supports_encryption: false
      export:
        eccn: "ECCN_EAR99"
        hts_applicable: false
        license_exception: "NLR"
      eula: {}
"""
    )
    with pytest.raises(ConfigError, match="either url or text"):
        load_config(f)


def test_local_file_path_relative_to_yaml(tmp_path):
    subdir = tmp_path / "sub"
    subdir.mkdir()
    f = subdir / "config.yaml"
    f.write_text(
        """
solution:
  logo: "../logo.png"
"""
    )
    cfg = load_config(f)
    assert cfg.logo == (subdir / ".." / "logo.png")


def test_container_asset_requires_repository_and_tag(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(
        """
solution:
  version:
    version_number: "1.0.0"
    release_tag: "GENERAL_AVAILABILITY"
    container_asset:
      deployment_instructions: "docker pull nginx"
    compliance:
      encryption:
        supports_encryption: false
      export:
        eccn: "ECCN_EAR99"
        hts_applicable: false
        license_exception: "NLR"
      eula:
        text: "terms"
"""
    )
    with pytest.raises(ConfigError, match="repository.*tag"):
        load_config(f)


def test_container_asset_refresh_skips_repository_tag_check(tmp_path):
    f = tmp_path / "cfg.yaml"
    f.write_text(
        """
solution:
  version:
    version_number: "1.0.0"
    release_tag: "GENERAL_AVAILABILITY"
    container_asset:
      refresh: true
    compliance:
      encryption:
        supports_encryption: false
      export:
        eccn: "ECCN_EAR99"
        hts_applicable: false
        license_exception: "NLR"
      eula:
        text: "terms"
"""
    )
    cfg = load_config(f)
    assert cfg.version.container_asset.refresh is True
