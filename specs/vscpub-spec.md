# vscpub Specification

## Overview

`vscpub` is a command-line tool for publishing and updating solutions on the
[VCF Solutions Catalog](https://eapi.broadcom.com/vcf/vsc/gtw/api/v3) (Broadcom).
It is driven by a YAML configuration file (conventionally named
`vscpub.yaml`) and wraps the VCF Solutions Catalog REST API.
Credentials are supplied exclusively via environment variables and are never
stored in the config file.

Two publication paths exist:

| Path | Status |
|---|---|
| Create a new solution | Stubbed — reserved for future implementation |
| Update an existing solution | **In scope** |

Two solution types are supported:

| Type | `form_factor` | `artifact_type` |
|---|---|---|
| VM image | `VIRTUAL_MACHINES` | `OVA` or `ISO` |
| Container image | `CONTAINERS` | `DOCKER` |


## Update-Existing Workflow

Updating an existing solution follows three ordered steps:

```
1. GET  /storage-location
        → Obtain a Google Cloud Storage pre-signed POST policy.
        → Required only when local files need to be uploaded
          (VM asset, container tar, logo, screenshots, documents).

2. POST {storage-location.url}  (multipart/form-data using the policy fields)
        → Upload each local file referenced in the config.
        → The resulting object URL is used as the asset or media URL in step 3.

3. PATCH /products/{product_id}             (if product-level fields changed)
   POST  /products/{product_id}/versions    (if version_number is new)
```

`vscpub publish` executes all three steps automatically.  It **errors** if
`version_number` already exists on the product. Existence of `version_number` is
checked before storage location creation to avoid unnecessarily consuming one
of the limited storage locations.


## Authentication

Credentials are provided via environment variables. The config file never
contains secrets.

Two authentication methods are supported — set the variables for exactly one:

**Option A — OAuth client credentials**

| Variable | Description |
|---|---|
| `VSCPUB_CLIENT_ID` | Client ID from a VMware Cloud Services OAuth app |
| `VSCPUB_CLIENT_SECRET` | Client secret from the same OAuth app |

**Option B — API refresh token**

| Variable | Description |
|---|---|
| `VSCPUB_API_TOKEN` | Refresh token generated from VMware Cloud Services Console |

`vscpub` errors at startup if neither pair is set, or if variables from both
options are present simultaneously.


## YAML Configuration Reference

The configuration file drives every `vscpub` command. Only fields relevant to
the operation being performed need to be present; the tool ignores unrecognised
keys rather than erroring. Note that all keys listed below will be unified under
the top level key `vscpub`

```yaml
# ── Solution ──────────────────────────────────────────────────────────────────
solution:
  # Required for the update-existing path.
  product_id: "prod-abc123"

  # Optional product-level fields.  Omit any field to leave it unchanged.
  display_name: "Enterprise Database Solution"   # max 150 chars
  logo: path/to/logo.png                         # local file → auto-uploaded
                                                 # supported: .png  .jpeg  .svg
                                                 # recommended resolution 150×150
  license: BYOL                                  # see Enum: License


  # ── Marketing ──────────────────────────────────────────────────────────────
  marketing:
    overview: "..."           # required if section present; max 250 chars
    description: "..."        # required if section present; max 10 000 chars
    feature_highlights:       # optional; up to 5 items
      - "High availability with automatic failover"
      - "Real-time data replication across nodes"
    images:                   # optional; local files → auto-uploaded
      - path/to/screenshot.png
    videos:                   # optional; .mov  .3gp  .mp4  or YouTube URLs
      - "https://www.youtube.com/watch?v=example123"


  # ── Support ────────────────────────────────────────────────────────────────
  support:
    website: "https://www.example.com/support"  # required if section present
    emails:                                      # required if section present
      - "support@example.com"
    summary: "..."            # optional; max 2000 chars
    phones:                   # optional
      - "+1-800-123-4567"
    resources:                # optional; end-user documents
      - name: "Installation Guide"
        url: "https://storage.googleapis.com/..."  # remote URL or local file path


  # ── Technical specifications ───────────────────────────────────────────────
  tech_specs:
    os_list: [UBUNTU, RHEL]            # optional; see Enum: OS
    category: DATABASES                # optional; see Enum: Category
    vcf_components: [VSPHERE, VSAN]    # optional; see Enum: VcfComponent
    technical_summary: "..."           # optional; max 2000 chars


  # ── Version ────────────────────────────────────────────────────────────────
  version:
    version_number: "1.2.0"                # immutable once created; max 20 chars
    release_tag: GENERAL_AVAILABILITY      # see Enum: ReleaseTag

    # ── VM asset ─────────────────────────────────────────────────────────────
    # Use when form_factor = VIRTUAL_MACHINES.
    # Mutually exclusive with container_asset.
    vm_asset:
      file: path/to/image.ova         # local .ova or .iso → auto-uploaded
      hash_algo: SHA256               # SHA1 | SHA256 | SHA512
      # hash_digest: "e3b0c4..."      # optional — auto-computed from file if omitted


    # ── Container asset ───────────────────────────────────────────────────────
    # Use when form_factor = CONTAINERS.
    # Mutually exclusive with vm_asset.  Exactly one mode must be specified.
    #
    # Mode 1 — Registry sync (docker pull)
    container_asset:
      repository: "bitnami/nginx"     # full public registry path
      tag: "2.1.0"
      deployment_instructions: "docker pull bitnami/nginx:2.1.0"  # optional

    # Mode 2 — Tar file upload
    # container_asset:
    #   file: path/to/image.tar       # local .tar → auto-uploaded
    #   repository: "my-org/my-app"   # destination repo name in VSC registry
    #   tag: "2.1.0"

    # Mode 3 — Refresh (re-pull from registry)
    # Only valid when the version is already in ACTIVE status.
    # container_asset:
    #   refresh: true


    # ── Compliance ─────────────────────────────────────────────────────────────
    compliance:
      encryption:
        supports_encryption: true          # required
        types:                             # required when supports_encryption: true
          - SECURITY_COMMUNICATION_PROTOCOLS  # see Enum: EncryptionType
        supports_non_standard_encryption: false  # optional; default false

      export:
        eccn: ECCN_EAR99                   # required; see Enum: ECCN
        hts_applicable: false              # required
        # hts: "8523.49.20.00"            # required when hts_applicable: true
        license_exception: NLR            # required; see Enum: LicenseException
        # ccats_number: "..."             # optional
        # ccats_document: path/to/ccats.pdf  # optional; local file → auto-uploaded

      eula:                                # exactly one of url or text required
        url: "https://storage.googleapis.com/..."
        # text: "Full EULA text..."        # mutually exclusive with url

      open_source:                         # optional; include for open-source solutions
        license_disclosure_url: "https://..."
        source_code_package_url: "https://..."
```


## CLI Reference

```
vscpub [--env ENV] [--dry-run] <command> [args]
```

### Global flags

| Flag | Values | Default | Description |
|---|---|---|---|
| `--env` | `dev` `qa` `verify` `prod` | `prod` | Target API environment |
| `--dry-run` | — | false | Print planned API calls without executing them |

### Commands

#### `vscpub storage create`

Fetches a GCS pre-signed POST policy from `GET /storage-location` and prints
it to stdout as JSON. Use this to obtain a single storage location that can
be shared across multiple upload commands within the same session, avoiding
redundant API calls.

```sh
vscpub storage create > /tmp/vsc-storage.json
vscpub publish --storage /tmp/vsc-storage.json config-a.yaml
vscpub publish --storage /tmp/vsc-storage.json config-b.yaml
```

The policy is temporary and has a server-defined expiry. If the policy has
expired when an upload is attempted, the GCS upload will fail with an error
from the remote — no client-side expiry check is performed.

Maps to `GET /storage-location`.

#### `vscpub publish [--storage <file>] <vscpub-publishing.yaml>`

The primary command for the update-existing path. Executes the full workflow:

1. Fetches a storage location (or uses the one supplied via `--storage`)
2. Uploads any local files referenced in the config (logo, images, assets, documents)
3. Calls `PATCH /products/{product_id}/versions` if any product-level fields are present
4. Calls `POST /products/{product_id}/versions/{version}` to create the new version

`--storage <file>` — path to a JSON file produced by `vscpub storage create`.
When omitted, a new storage location is fetched automatically.

**Errors if `version_number` already exists on the product.**

#### `vscpub product list`

Lists all products for the authenticated organisation with their IDs and
statuses.  
Maps to `GET /products`.

#### `vscpub product get <product-id>`

Prints full product details including all version numbers and their statuses.  
Maps to `GET /products/{productId}`.

#### `vscpub product update [--storage <file>] <vscpub-publishing.yaml>`

Updates product-level metadata (display name, logo, marketing, support,
tech specs, license) without touching any version. Accepts `--storage <file>`
when the update includes local file uploads (e.g. a new logo or screenshot).  
Maps to `PATCH /products/{productId}`.

#### `vscpub version add [--storage <file>] <vscpub-publishing.yaml>`

Explicit alias for creating a new version on an existing product. Equivalent
to `vscpub publish` but skips the product-level metadata update step.  
Maps to `POST /products/{productId}/versions`.


## Enum Reference

### License
| Value | Description |
|---|---|
| `FREE` | No cost, no license key required |
| `BYOL` | Bring Your Own License |
| `TRIAL` | Limited evaluation period |
| `OPEN_SOURCE` | Open source (MIT, Apache 2.0, GPL, etc.) |

### ReleaseTag
`GENERAL_AVAILABILITY` `DEVELOPER_RELEASE` `ALPHA_RELEASE` `BETA_RELEASE`
`RELEASE_CANDIDATE` `MAJOR_RELEASE` `MINOR_RELEASE` `SECURITY_RELEASE`
`MAINTENANCE_RELEASE`

### OS
`DEBIAN` `I_OS` `RASPBERRY_PI` `ANDROID` `CHROME` `SUSE` `RHEL` `UBUNTU`
`MAC_OS` `CENT_OS` `LINUX` `UNIX` `WINDOWS`

### Category
`AI_MACHINE_LEARNING` `ANALYTICS` `BUSINESS_APPLICATION_SERVICES`
`BUSINESS_TOOLS` `COMPUTE` `DATABASES` `DEVELOPER_TOOLS` `DEV_OPS`
`HARDWARE` `IDENTITY` `INTERNET_OF_THINGS` `MANAGEMENT_AND_MONITORING`
`NETWORKING` `OTHER_CATEGORY` `STORAGE` `TELCO` `FINANCIAL_SERVICES`

### VcfComponent
`NSX` `OTHER_VCF_COMP` `VMWARE_LIVE_RECOVERY` `TELCO_CLOUD`
`VCF_OPERATIONS_FOR_LOGS` `VCF_OPERATIONS_FOR_NETWORKS` `VSAN`
`VSPHERE_KUBERNETES_SERVICE` `VCF_AUTOMATION` `VCF_OPERATIONS` `VSPHERE`

### EncryptionType
| Value | Description |
|---|---|
| `USER_AUTHENTICATION` | Encryption for user authentication |
| `CONTENT_PROTECTION` | Encryption for content protection |
| `SECURITY_COMMUNICATION_PROTOCOLS` | TLS, SSL, and similar protocols |
| `SECURING_DATA_AT_REST` | Encryption for stored data |
| `INTENDED_AS_NETWORK_INFRA` | Network infrastructure with encryption |
| `NON_STANDARD_ENCRYPTION` | Non-standard algorithms or methods |
| `OTHER_ENCRYPTION` | Other encryption capabilities |

### ECCN
| Value | Label |
|---|---|
| `ECCN_5D992c` | 5D992.c |
| `ECCN_EAR99` | EAR99 |
| `ECCN_5D002c` | 5D002c.1(b)(1) and (b)(3) |
| `ECCN_OTHER` | Other — supply `eccn_other: "..."` alongside |

### LicenseException
| Value | Description |
|---|---|
| `ENC_RESTRICTED` | Restricted encryption license exception |
| `ENC_UNRESTRICTED` | Unrestricted encryption license exception |
| `TSU_UNRESTRICTED` | Technology and Software Unrestricted |
| `NLR` | No License Required |
