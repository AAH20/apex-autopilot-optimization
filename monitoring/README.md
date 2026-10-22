# apex-autopilot-optimization observability stack
#
# Prerequisites:
#   pip install prometheus-client  # if serving metrics from a Python app
#
# Run the stack:
#   docker compose up -d
#
# Then scrape /metrics from your SwarmObserver-instrumented application
# at http://localhost:9090 (Prometheus) and view dashboards at
# http://localhost:3000 (Grafana, admin/admin).
#
# Metrics endpoint (expose from your FastAPI/Flask/uvicorn app):
#   GET /metrics  -> text/plain; version=0.0.4  (Prometheus text format)
#
# Alert rules are loaded from monitoring/alert-rules.yml into Prometheus.
#
# To validate locally without Docker:
#   python3 -c "
#     from apex_autopilot_optimization.observability.metrics import generate_latest
#     print(generate_latest())
#   "
