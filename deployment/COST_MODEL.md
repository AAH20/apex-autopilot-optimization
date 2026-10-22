# Multi-Cloud Free-Tier Cost Model

All figures are **monthly, always-free ceilings**. Projected spend = $0 if usage stays within these limits. Anything above is billed at on-demand rates.

## AWS (always-free)

| Service | Free allowance | Ceiling risk | Unit overage |
|---------|---------------|--------------|--------------|
| Lambda | 1M requests + 400K GB-s compute | High traffic | $0.20 / 1M req |
| DynamoDB | 25 GB storage, 25 WCU + 25 RCU | Storage growth | $0.25/GB-month |
| S3 | 5 GB, 20K GET, 2K PUT | Object count/ops | $0.023/GB + request fees |
| API Gateway (HTTP) | 1M calls/mo | API volume | $1.00 / 1M calls |
| CloudFront | 1 TB out + 10M req/mo | Egress | $0.085/GB |
| ECR | 500 MB/mo | Image size | Standard ECR rates |
| CloudWatch Logs | 5 GB ingestion, 10 custom metrics | Log volume | $0.50/GB |

**AWS projected monthly cost: $0** (within allowances)

## GCP (always-free)

| Service | Free allowance | Ceiling risk | Unit overage |
|---------|---------------|--------------|--------------|
| Cloud Run | 2M requests/mo | Request volume | $0.40 / 1M req |
| Cloud Storage | 5 GB (US regions) | Storage | $0.020/GB |
| Firestore Native | 1 GB storage | Document growth | $0.18/GB |
| Cloud Functions (2nd gen) | 2M invocations/mo | Invocation volume | $0.40 / 1M invocations |
| Compute e2-micro | 1 instance (us-*), always free | Only 1 instance | Standard e2-micro rate |

**GCP projected monthly cost: $0** (within allowances)

## Azure (always-free + time-limited)

| Service | Free allowance | Type | Ceiling risk |
|---------|---------------|------|--------------|
| Functions Consumption | 1M executions/mo | Always-free | Execution volume |
| Container Apps | 2M requests/mo | Always-free | Request volume |
| Cosmos DB serverless | 1,000 RU/s + 25 GB | Always-free | RU/s + storage |
| Static Web Apps Free | 100 GB bandwidth | Always-free | Bandwidth |
| Blob Hot | 5 GB | 12-month trial | Converts to paid after 12 mo |
| B1s VM | 750 h/mo | 12-month trial | Converts to paid after 12 mo |

**Azure projected monthly cost: $0** (within allowances; exclude Blob/B1s from hot path)

## Aggregate ceiling

| Provider | Projected monthly cost | Hard cap policy |
|----------|----------------------|-----------------|
| AWS | $0 | $0 budget + 50/80/100% alerts |
| GCP | $0 | $0 budget + 50/80/100% alerts |
| Azure | $0 | $0 budget + 50/80/100% alerts |
| **Total** | **$0/mo** | **Auto-suspend at 100%** |

## Overage scenario (example)

If Lambda requests hit 2M/mo (2x free):
- Lambda overage: 1M extra × $0.20 = $0.20
- Still negligible; the design prioritizes staying under ceilings via caching (Firestore) and CDN (CloudFront) rather than paying overage.

## Budgets

Set one budget per provider at $0.50 (effectively a tripwire) with alerts at 50/80/100% of the always-free service ceilings. Any non-zero actual spend triggers investigation.
