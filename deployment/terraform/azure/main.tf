# Azure — always-free services (hot path) + clearly-marked 12-month trial services.
# Functions Consumption (1M exec/mo), Cosmos DB serverless (1k RU/s + 25 GB),
# Static Web Apps Free (100 GB bw).
# NOTE: azurerm_storage_account (Blob 5 GB) and B1s App Service plan are
# 12-month free-trial, NOT always-free — excluded from hot path.

resource "azurerm_resource_group" "rg" {
  name     = "mcft-rg"
  location = var.azure_location
}

# Storage account used by Function Apps (12-month free tier — non-critical).
resource "azurerm_storage_account" "func_storage" {
  name                     = "mcftfunc"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

# Consumption (Y1) plan — Azure Functions always-free tier.
resource "azurerm_app_service_plan" "func_plan" {
  name                = "mcft-func-plan"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  kind                = "FunctionApp"
  reserved            = false

  sku {
    tier = "Y1"
    size = "Y1"
  }
}

resource "azurerm_function_app" "api_failover" {
  name                       = "mcft-api-failover"
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  app_service_plan_id        = azurerm_app_service_plan.func_plan.id
  storage_account_name       = azurerm_storage_account.func_storage.name
  storage_account_access_key = azurerm_storage_account.func_storage.primary_access_key
  version                    = "~4"
  os_type                    = "Linux"
  kind                       = "FunctionApp"

  site_config {
    always_on = false
  }

  app_settings = {
    AzureFunctionsJobHost__logging__isEnabled = "true"
  }
}

# Cosmos DB serverless — always-free: 1,000 RU/s + 25 GB.
resource "azurerm_cosmosdb_account" "state_replica" {
  name                = "mcft-cosmos"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  enable_automatic_failover = false

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.rg.location
    failover_priority = 0
  }

  capabilities {
    name = "EnableServerless"
  }
}

resource "azurerm_cosmosdb_sql_database" "state" {
  name                = "mcft-state"
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.state_replica.name
}

resource "azurerm_cosmosdb_sql_container" "sessions" {
  name                = "sessions"
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.state_replica.name
  database_id         = azurerm_cosmosdb_sql_database.state.id
  partition_key_path = "/pk"

  indexing_policy {
    indexing_mode = "consistent"
    included_paths {
      path = "/*"
    }
  }
}

# Static Web Apps Free — 100 GB bandwidth/mo, always-free.
resource "azurerm_static_site" "edge" {
  name                = "mcft-edge"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Free"
  repository_url      = "https://github.com/example/mcft-web"
  branch              = "main"

  build_properties {
    app_location = "/"
  }
}

# Metric alert: fire if Azure Functions executions approach the 1M/mo ceiling.
resource "azurerm_monitor_metric_alert" "functions_quota" {
  name                = "mcft-azure-functions-quota"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  severity            = "2"
  enabled             = true
  scopes              = [azurerm_function_app.api_failover.id]
  frequency           = "PT1M"
  window_size         = "PT5M"
  aggregation         = "Total"

  criteria {
    metric_namespace = "microsoft.web/sites"
    metric_name      = "Requests"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 800000  # 80% of 1M free executions
    time_aggregation = "Total"
  }

  action {
    action_group_id = azurerm_monitor_action_group.alerts.id
    action_group_title = "mcft-alerts"
  }
}

resource "azurerm_monitor_action_group" "alerts" {
  name                = "mcft-alerts"
  resource_group_name = azurerm_resource_group.rg.name
  short_name          = "mcft"

  email_receiver {
    name       = "finops"
    email_address = var.budget_alert_email
  }
}
