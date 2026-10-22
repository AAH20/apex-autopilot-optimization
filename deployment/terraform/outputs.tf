output "aws_dynamodb_table_name" {
  value       = aws_dynamodb_table.app_state.name
  description = "DynamoDB table used for application state (always-free tier)."
}

output "aws_s3_bucket_id" {
  value       = aws_s3_bucket.assets.id
  description = "S3 bucket for static assets (5 GB always-free)."
}

output "gcp_firestore_database" {
  value       = google_firestore_database.metadata.name
  description = "Firestore database for metadata cache (1 GB always-free)."
}

output "gcp_cloud_run_url" {
  value       = google_cloud_run_service.api_burst.url
  description = "GCP Cloud Run service URL (burst capacity, 2M req/mo)."
}

output "azure_function_app_host" {
  value       = azurerm_function_app.api_failover.default_hostname
  description = "Azure Function App hostname (failover, 1M exec/mo)."
}

output "azure_cosmosdb_endpoint" {
  value       = azurerm_cosmosdb_account.state_replica.endpoint
  description = "Cosmos DB endpoint (geo-replica, 1k RU/s + 25 GB)."
}

output "estimated_monthly_cost_usd" {
  value       = 0
  description = "Estimated monthly cost when all usage stays within always-free allowances."
}
