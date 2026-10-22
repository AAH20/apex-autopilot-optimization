# Multi-Cloud Free-Tier Deployment with FinOps

**Goal:** Run a production-grade, multi-cloud serverless application entirely within **always-free** allowances across AWS, GCP, and Azure — zero committed spend, with hard budget guardrails and FinOps observability.

**Constraint:** Azure free-tier subscription (the account that anchors this design). AWS and GCP are added as secondary/tertiary free-tier regions for redundancy, burst capacity, and vendor diversification. No credit-funded (trial) services are used as the primary path; credits expire, always-free allowances do not.

---

## 1. Design principles

1. **Always-free only.** Every resource must belong to a provider's always-free tier (monthly-reset allowances that never expire). 12-month trial and credit-funded services are excluded from the hot path and flagged where unavoidable.
2. **Single pane of glass.** OpenCost aggregates AWS + GCP + Azure cost/usage into one Prometheus-backed view; Grafana dashboards show per-provider, per-service, per-tag spend.
3. **Governance by policy.** Cloud Custodian enforces tagging, auto-stops untagged/idle resources, and deletes orphan snapshots — preventive, not detective.
4. **Shift-left cost.** Infracost prices every Terraform PR before merge; a $0/mo budget breach fails CI.
5. **Hard budget caps.** $0 budgets with alerts at 50/80/100% of each provider's always-free ceiling; 100% triggers automated resource suspension via Cloud Custodian.

---

## 2. Service selection (always-free)

| Layer | AWS (us-east-1) | GCP (us-central1) | Azure (East US) | Role |
|-------|----------------|-------------------|-----------------|------|
| Edge / CDN | CloudFront 1 TB out + 10M req/mo | Cloud CDN (pay-as-you-go, cached) | Static Web Apps Free 100 GB bw | Global entry; primary = CloudFront |
| API / Compute | Lambda 1M req + 400K GB-s/mo | Cloud Run 2M req/mo | Functions Consumption 1M exec/mo | Primary API (AWS); failover (Azure); burst (GCP) |
| Database | DynamoDB 25 GB + 25 WCU/RCU | Firestore Native 1 GB | Cosmos DB serverless 1k RU/s + 25 GB | Session/state (AWS); cache/metadata (GCP); geo-replica (Azure) |
| Object storage | S3 5 GB + 20K GET / 2K PUT | Cloud Storage 5 GB (US) | Blob Hot 5 GB (12-mo trial ⚠️) | Assets (AWS); archive (GCP); logs (Azure) |
| Bastion / cron VM | — | e2-micro 1 instance (always free) | B1s 750 h/mo (12-mo ⚠️) | Scheduled jobs, health checks |
| Container registry | ECR 500 MB/mo | — | — | Image storage for Cloud Run/Azure Container Apps |
| Observability | CloudWatch 5 GB logs + 10 metrics | Cloud Operations (trial-limited) | Azure Monitor (trial-limited) | Logs/metrics; OpenCost overlays cost |

⚠️ Azure Blob 5 GB and B1s VM are 12-month free-trial, not always-free. They are used for non-critical archive/cron only; the hot path never depends on them.

---

## 3. Architecture

```
                    Internet
                       |
              +--------v--------+
              |  CloudFront (AWS) |  <-- always-free edge, 1 TB out/mo
              +--------+--------+
                       |
        +--------------+--------------+--------------+
        |              |              |              |
   API Gateway   Azure Functions  GCP Cloud Run   (failover/burst)
   (AWS, 1M)     (1M exec/mo)     (2M req/mo)
        |              |              |
        +--------------+--------------+
                       |
              +--------v--------+
              |  Traffic Manager  |  (priority routing: AWS -> Azure -> GCP)
              +--------+--------+
                       |
        +--------------+--------------+--------------+
        |              |              |              |
   DynamoDB      Cosmos DB        Firestore       (cache/metadata)
   (AWS state)   (Azure replica)  (GCP, 1 GB)
        |
   S3 (assets)  <-- Cloud Storage (GCP archive)  <-- Blob (Azure logs)
```

- **Primary path:** CloudFront → API Gateway → Lambda → DynamoDB + S3 (AWS).
- **Failover:** If AWS is unavailable or near quota, Azure Front Door/Static Web Apps routes to Azure Functions → Cosmos DB.
- **Burst:** GCP Cloud Run absorbs traffic spikes; Firestore caches read-heavy metadata.
- **Data residency:** Each provider's resources stay in its home region; no cross-region paid data transfer between providers (egress across public internet is bounded by CloudFront's 1 TB free allowance).

---

## 4. FinOps operating model

| Pillar | Tool | Cadence | Action |
|--------|------|---------|--------|
| Visibility | OpenCost + Prometheus + Grafana | Real-time | Per-provider/service/tag cost dashboards; FOCUS-aligned export |
| Governance | Cloud Custodian | Continuous (mode: periodic) | Tag enforcement, orphan cleanup, idle-resource shutdown |
| Planning | Infracost (CI) | Per PR | Cost estimate comment; $0 delta gate |
| Budgeting | Native provider budgets + CloudWatch/GCP/Azure alerts | Monthly | 50/80/100% alerts; 100% → auto-suspend non-essential resources |
| Chargeback | Tags + OpenCost allocation | Monthly | Allocate spend by `Team`, `Project`, `Environment=free-tier` |

**Tagging standard (mandatory on every resource):** `Environment=free-tier`, `Project`, `Owner`, `CloudProvider`, `CostCenter`, `ManagedBy=terraform`.

**Budget policy:** $0 committed spend per provider. Alerts fire when projected monthly cost exceeds 50% of the always-free ceiling (e.g., DynamoDB storage trending toward 25 GB). At 100%, Cloud Custodian stops non-essential resources and sends a page.

---

## 5. Free-tier risk register

| Risk | Mitigation |
|------|------------|
| AWS new-account "Free Plan" auto-closes after 6 months (post-Jul-2025) | Use Paid Plan account or legacy account; rely only on always-free services; monitor account status |
| Azure 12-month services (Blob, B1s) convert to paid after 1 year | Exclude from hot path; set expiry alerts at month 10 |
| Egress between providers exceeds free allowances | Keep traffic within each provider's region; use CloudFront 1 TB as buffer |
| Hidden charges (API requests, put/get ops) | CloudWatch/GCP Monitoring/Azure Monitor alarms on request counts; Custodian quota policies |
| Trial credits accidentally consumed | Disable credit spend at account level; budget alerts at $0.01 |

---

## 6. Deliverables in this directory

- `terraform/` — provider configs + always-free resource definitions for AWS, GCP, Azure
- `finops/custodian/policies.yaml` — Cloud Custodian governance policies
- `finops/budgets/` — per-provider budget & alert definitions
- `monitoring/opencost/values.yaml` — OpenCost Helm values (multi-cloud)
- `ci/github-actions/deploy.yml` — CI/CD with Infracost shift-left gate
- `COST_MODEL.md` — monthly free-tier cost model & ceiling math
- `runbooks/budget-breach.md` — incident response for budget breach
