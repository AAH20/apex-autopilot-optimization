# Runbook — Budget breach (free-tier ceiling approached/exceeded)
# Trigger: any provider budget notification at 80% or 100%, or OpenCost
# projected-monthly-cost gauge > $0.50.

## Severity
- 80% of ceiling: WARNING — investigate within 24h
- 100% of ceiling: CRITICAL — act within 1h to avoid billable overage

## Immediate response (100% breach)
1. Acknowledge the budget alert (email / SNS / Azure action group).
2. Open OpenCost/Grafana dashboard: identify provider + service driving spend.
3. Confirm whether usage is legitimate traffic or a runaway resource (loop, missing cache, hot key).
4. If runaway: run Cloud Custodian policy `freeze-non-free-tier-resources` to stop non-compliant resources.
5. If legitimate but over ceiling: scale down the offending service (reduce Lambda concurrency, Cloud Run instances, Cosmos RU/s) or shift traffic to another provider's free allowance via CloudFront / Traffic Manager priority routing.

## Containment
- Disable auto-scaling; pin instance counts to 1 (e2-micro, Lambda reserved concurrency = 0).
- Set DynamoDB to on-demand with a max WCU/RCU cap, or switch reads to Firestore cache.
- Serve static assets from CloudFront (1 TB free) rather than direct S3/Blob GETs.
- Pause non-essential cron jobs on the bastion VM.

## Recovery
- Once spend is below 50% of ceiling and trending down, re-enable services one at a time.
- Add a Cloud Custodian quota policy or Terraform guard so the service cannot regrow past the free ceiling.
- Update the cost model (COST_MODEL.md) and budget thresholds.

## Prevention (ongoing)
- Infracost gate on every PR: any estimated monthly cost > $0 fails CI.
- Monthly FinOps review: actual vs always-free ceiling per provider.
- Tag audit: untagged resources are auto-stopped by Custodian after 24h.
- Credits: never enable credit-funded services; disable "allow overspend" at account level.

## Contacts
- FinOps on-call: finops@example.com
- Escalation: platform-lead@example.com
