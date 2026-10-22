# FinOps tagging standard — mandatory on every resource, all three providers.
# Used by Cloud Custodian governance and OpenCost chargeback allocation.

Required tags:
  - Environment   # must equal "free-tier" for resources under the $0 budget
  - Project       # e.g. "mcft"
  - Owner         # team / person responsible
  - CostCenter    # finance code for chargeback
  - CloudProvider # aws | gcp | azure
  - ManagedBy     # terraform | custodian | manual

Tag inheritance:
  - AWS:  default_tags block in provider + per-resource tags
  - GCP:  labels (lowercase, hyphenated) mapped from common_tags
  - Azure: tags object on every resource + default_tags in provider

Enforcement:
  - Cloud Custodian `enforce-mandatory-tags` policies mark non-compliant
    resources for stop/delete after a grace period.
  - CI rejects Terraform plans that add resources missing required tags
    (OPA / Sentinel-style check — implemented as a plan JSON grep in CI).
  - Untagged resources are excluded from OpenCost allocation and flagged
    as "untracked spend" on the FinOps dashboard.

Chargeback granularity:
  - By provider (AWS / GCP / Azure)
  - By service (Lambda / Cloud Run / Functions / DynamoDB / ...)
  - By tag combination (Project + Environment + CostCenter)
