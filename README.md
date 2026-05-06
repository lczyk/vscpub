# vscpub

CLI for publishing solutions to the VMware Solutions Catalog (VSC).

## Installation

```
uv tool install git+https://github.com/canonical/vscpub.git
```

## Authentication

Set one of the following environment variables:

- `VSCPUB_API_TOKEN` — API token
- `VSCPUB_CLIENT_ID` + `VSCPUB_CLIENT_SECRET` — OAuth client credentials

## Commands

### Global flags

| Flag | Description |
|------|-------------|
| `--dry-run` | Print API calls without executing mutations |
| `--verbose` | Log API calls to stderr |

---

### `product list`

List all products for the authenticated organisation.

```
vscpub product list
```

### `product get <product_id>`

Print full product details as JSON.

```
vscpub product get <product_id>
```

### `product update <yaml_file>`

Update product metadata (name, description, logo, etc.) without creating a new version.
Only fields present in the config are sent to the API — omitting a field leaves the existing value unchanged.
If the config references local files (logo, marketing images), they are uploaded to GCS automatically.
Pass `--storage` to reuse an existing pre-signed policy instead of fetching a new one.

```
vscpub product update solution.yaml
vscpub product update --storage policy.json solution.yaml
```

---

### `version get <product_id> <version_number>`

Print details for a specific product version as JSON.

```
vscpub version get <product_id> 1.2.0
```

### `version add <yaml_file>`

Add a new version to an existing product without touching its metadata.

```
vscpub version add solution.yaml
vscpub version add --storage policy.json solution.yaml
```

---

### `storage create`

Fetch a GCS pre-signed POST policy and print it as JSON. Use this to obtain upload credentials before running `product update` or `version add` with `--storage`.

```
vscpub storage create > policy.json
```

---

### `publish <yaml_file>`

Full workflow: upload assets, update product metadata, and add a new version in one command. If `--storage` points to a non-existent file, a new storage policy is fetched and saved there automatically.

```
vscpub publish solution.yaml
vscpub publish --storage policy.json solution.yaml
```

---

## Configuration file

Commands that take a `<yaml_file>` argument expect a YAML file with a top-level `solution` key.

```yaml
solution:
  product_id: my-product-id      # required for update/version add/publish
  display_name: My Solution
  logo: logo.png                 # path relative to the YAML file
  license: BYOL                  # e.g. BYOL, PAYG

  marketing:
    overview: "Short overview"
    description: "Long description"
    feature_highlights:
      - "Feature one"
    images:
      - screenshot.png
    videos:
      - "https://example.com/demo"

  support:
    website: "https://support.example.com"
    emails:
      - support@example.com
    summary: "24/7 support"
    phones:
      - "+1 800 000 0000"
    resources:
      - name: Documentation
        url: "https://docs.example.com"

  tech_specs:
    os_list:
      - UBUNTU
    category: NETWORKING
    vcf_components:
      - VCF_OPERATIONS
    technical_summary: "..."
    form_factor: VIRTUAL_MACHINES
    artifact_type: OVA

  version:
    version_number: "1.2.0"
    release_tag: GENERAL_AVAILABILITY

    # Provide either vm_asset or container_asset, not both.
    vm_asset:
      file: image.ova            # path relative to the YAML file
      hash_algo: SHA256          # required when file is set; SHA1 | SHA256 | SHA512
      hash_digest: "abc123..."   # required when file is set

    # container_asset:
    #   repository: registry.example.com/my-image
    #   tag: "1.2.0"
    #   deployment_instructions: "..."
    #   file: bundle.tar          # optional
    #   refresh: false

    compliance:
      encryption:
        supports_encryption: true
        types:
          - SECURITY_COMMUNICATION_PROTOCOLS
        supports_non_standard_encryption: false

      export:
        eccn: ECCN_EAR99
        hts_applicable: false
        # eccn_other: "..."       # required when eccn is ECCN_OTHER
        # hts: "..."
        # license_exception: "..."
        # ccats_number: "..."
        # ccats_document: ccats.pdf

      eula:
        url: "https://example.com/eula"
        # text: "..."             # mutually exclusive with url

      # open_source:
      #   license_disclosure_url: "https://example.com/oss"
      #   source_code_package_url: "https://example.com/src.tar.gz"
```
