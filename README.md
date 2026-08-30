# Sample Infra Monitoring

This is a sample project to demonstrate how to ingest infra metrics into CubeAPM using OpenTelemetry Collector. It collects metrics from various sources and feeds them into CubeAPM. This repository has a docker compose file to set up all these services conveniently.

## Setup

Clone this repository and go to the project directory. Then run the following commands

```bash
python3 generate_mock_metrics.py   # generates mock-metrics/ and targets/ (required before first run)
docker compose up -d
```

## Notes

1. Detailed documentation for each infra component is available at [https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver).
2. To get Kafka metrics, you need to create a topic and produce some messages. Open Kafdrop at [http://localhost:19000](http://localhost:19000) and create a topic named `mytopic`. Then run the following command to produce messages to the topic:
  ```bash
   docker exec -it infra_monitoring-kafka-1 kafka-console-producer --broker-list localhost:9092 --topic mytopic
  ```
   The producer will wait for input. You can you can enter one message per line and finalize the input by pressing `Ctrl+D`. This will produce messages to the topic.
3. To get RabbitMQ metrics, you need to create a queue and publish some messages. Open RabbitMQ management UI at [http://localhost:15672](http://localhost:15672) and login with the default credentials YOUR_USERNAME/YOUR_PASSWORD. Create a queue and publish some messages to it.



## Testing the OTel Collector with Mock Metrics (File-based Discovery)

This section tests the setup with 50 mock nginx and 50 mock redis servers using file-based service discovery. No external dependencies required — everything runs in Docker.

### Step 1 — Generate mock metrics and start the stack

```bash
python3 generate_mock_metrics.py   # creates mock-metrics/ and targets/ — run once before first start
docker compose up -d
```

Verify all 6 containers are up:

```bash
docker compose ps
```

Expected containers: `mock-metrics-server`, `otel-collector`, `prometheus`, `grafana`, `nginx`, `redis`.

### Step 2 — Verify the mock metrics server

```bash
curl http://localhost:8090/metrics/nginx-1.txt
curl http://localhost:8090/metrics/redis-50.txt
```

You should see Prometheus-format text with metric names and values. If you get a 404, either the `mock-metrics` directory is not mounted correctly or `generate_mock_metrics.py` hasn't been run yet.

### Step 3 — Verify the OTel collector is scraping

```bash
docker compose logs -f otel-collector
```

Within 60 seconds you should see blocks like:

```
-> server: Str(nginx-23)
-> env: Str(prod)
-> region: Str(us-east)
nginx_connections_current: 142
```



### Step 4 — Verify Prometheus has the data

Open `http://localhost:9090` and run these queries:

```promql
# Should return 50 time series — one per server
count(nginx_connections_current{state="active"})

# Should return 50 time series
count(redis_memory_used)

# Check a specific server
redis_memory_used{server="redis-1"}

# Check all prod servers
nginx_connections_current{env="prod", state="active"}
```

If count returns 0, Prometheus hasn't scraped yet — wait 60 seconds and retry.

### Step 5 — Visualize in Grafana

1. Open `http://localhost:3000` — login: **admin / admin**
2. Go to **Explore** (compass icon in the left sidebar)
3. Select **Prometheus** datasource
4. Try these queries:

```promql
# Memory used across all 50 redis servers
redis_memory_used

# Top 10 redis servers by memory
topk(10, redis_memory_used)

# Active connections per nginx server, prod only
nginx_connections_current{state="active", env="prod"}

# Average memory grouped by region
avg by (region) (redis_memory_used)

# Total active connections grouped by environment
sum by (env) (nginx_connections_current{state="active"})
```

> **Note:** The mock metrics files contain static values generated once by `generate_mock_metrics.py`. Counter metrics (e.g. `nginx_requests_total`, `redis_commands_processed_total`) will show a flat line — `rate()` and `increase()` queries return 0. Use gauge metrics (`nginx_connections_current`, `redis_memory_used`, etc.) for meaningful graphs.



### Step 6 — Test dynamic target updates (no restart needed)

This is the key feature of Approach 2 — adding a server without restarting the collector.

**a) Add a new entry to** `targets/nginx-targets.json`**:**

```json
{
  "targets": ["mock-metrics-server:80"],
  "labels": {
    "__metrics_path__": "/metrics/nginx-1.txt",
    "server": "nginx-51",
    "env": "prod",
    "region": "us-east",
    "service": "nginx"
  }
}
```

**b) Create a metrics file for it:**

```bash
cp mock-metrics/nginx-1.txt mock-metrics/nginx-51.txt
```

**c) Wait 30 seconds**, then query Prometheus:

```promql
nginx_connections_current{server="nginx-51"}
```

The new server appears without restarting anything.

### Step 7 — Tear down

```bash
docker compose down
```

> Both Prometheus and Grafana data are preserved across restarts via Docker volumes (`prometheus_data` and `grafana_data`). To wipe all data, run `docker compose down -v`.

---



## Contributing

Please feel free to raise PR for any enhancements - additional integrations, version updates, documentation updates, etc.