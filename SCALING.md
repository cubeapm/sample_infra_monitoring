# Architecture & Setup Decisions

## 1. Scope: Redis and Nginx only

**Decision:** Commented out all other receivers (aerospike, apache, elasticsearch, haproxy, kafka, memcached, mongodb, mongodbatlas, mysql, postgresql, rabbitmq) from both `otel-collector-config.yml` and `docker-compose.yml`.

**Why:** Focused local testing environment. Other services remain in the config but are disabled — re-enable by uncommenting in `otel-collector-config.yml` under `service.pipelines.metrics.receivers` and the corresponding service in `docker-compose.yml`.

---

## 2. Visualization: Prometheus + Grafana

**Decision:** Use Prometheus + Grafana as the local observability stack.

**Why:** CubeAPM requires an account token and a running CubeAPM instance. For local development and testing, Prometheus + Grafana is fully self-contained with no external dependencies.

**CubeAPM status:** The `otlphttp` exporter is defined but commented out of the pipeline. When CubeAPM is available, uncomment `- otlphttp` in `otel-collector-config.yml` under `service.pipelines.metrics.exporters`.

**Stack:**


| Service        | Port | Purpose                                  |
| -------------- | ---- | ---------------------------------------- |
| otel-collector | 8889 | Exposes metrics for Prometheus to scrape |
| Prometheus     | 9090 | Scrapes and stores metrics               |
| Grafana        | 3000 | Visualizes metrics (login: admin/admin)  |


**Grafana datasource** is auto-provisioned via `grafana/provisioning/datasources/datasource.yml` — no manual setup needed.

---



## 3. Debug exporter enabled

**Decision:** The `debug` exporter is active in the pipeline alongside the `prometheus` exporter.

**Why:** Lets you verify metrics are being collected by running `docker compose logs -f otel-collector` without needing any UI. Useful during development to confirm receivers are working.

**To disable:** Comment out `- debug` in `service.pipelines.metrics.exporters` in `otel-collector-config.yml`.

---



## 4. Scaling to multiple servers

Five approaches depending on scale and environment. **Implemented in this project: Approach 2** — file-based discovery for 100 mock servers (50 nginx + 50 redis).

**Approach 1: Named receiver instances (< 20 servers)**

You hardcode every server directly in the collector config. The collector knows exactly who to talk to because you told it explicitly.

```
otel-collector-config.yml      otel-collector              Grafana
┌────────────────────────┐     ┌─────────────┐        ┌──────────────┐
│ redis/prod-1: :6379    │────►│             ├─push──►│ 3 redis      │
│ redis/prod-2: :6380    │────►│ scrapes all │        │ servers on   │
│ redis/prod-3: :6381    │────►│ listed      │        │ dashboard    │
└────────────────────────┘     │ receivers   │        └──────────────┘
    ↑ you edit this            └─────────────┘
    new server = add block
    + restart collector
```

**The key limitation:** Every change requires editing the config file and restarting the collector. Fine when you have 5 servers that never change. Painful at 50.

```yaml
receivers:
  redis/prod-1:
    endpoint: prod-redis-1:6379
    collection_interval: 60s
  redis/prod-2:
    endpoint: prod-redis-2:6379
    collection_interval: 60s
  nginx/server-1:
    endpoint: http://nginx-1:80/status
    collection_interval: 60s

service:
  pipelines:
    metrics:
      receivers: [redis/prod-1, redis/prod-2, nginx/server-1]
```


| Pros                   | Cons                                    |
| ---------------------- | --------------------------------------- |
| Simple, fully explicit | Config grows large at 50+ servers       |
| Easy to debug          | Restart collector to add/remove servers |
| No extra tools needed  | Manual process, error prone at scale    |




---

**Approach 2: File-based discovery (20–200 servers) ✅ Current approach**

Think of it as an **address book the collector watches**. Servers are listed in a JSON file. The collector re-reads it every 30 seconds — no restart needed.

```
targets/nginx.json          otel-collector              Grafana
┌──────────────────┐        ┌─────────────┐        ┌──────────────┐
│ nginx-1:80  prod │◄─watch─┤             ├─push──►│ 3 nginx      │
│ nginx-2:80  prod │        │ scrapes all │        │ servers on   │
│ nginx-3:80  stag │        │ listed      │        │ dashboard    │
└──────────────────┘        │ targets     │        └──────────────┘
    ↑ you edit this         └─────────────┘
    new server = add a line
    no restart needed
```

**The key benefit:** Your provisioning tool (Terraform, Ansible, a shell script) just writes to that JSON file when it creates/destroys a server. The collector picks it up — no human involved, no restart.

**How it works:**
The collector watches a JSON file on disk. When you add a new server to the file, the collector picks it up automatically on the next refresh interval.

```yaml
# otel-collector-config.yml
receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: nginx
          # nginx stub_status does not serve Prometheus format — requires nginx-prometheus-exporter
          # targets here should point to nginx-exporter instances, not nginx directly
          file_sd_configs:
            - files: ['/etc/otelcol/targets/nginx-exporters.json']
              refresh_interval: 30s
```

```json
// nginx.json — edit this file to add/remove servers
[
  { "targets": ["nginx-1:80"], "labels": { "env": "prod", "region": "us-east" } },
  { "targets": ["nginx-2:80"], "labels": { "env": "prod", "region": "us-west" } },
  { "targets": ["nginx-3:80"], "labels": { "env": "staging" } }
]
```

For Redis (which uses TCP, not HTTP), pair with `[redis_exporter](https://github.com/oliver006/redis_exporter)` — a single process that monitors hundreds of Redis instances and exposes them as HTTP metrics for the prometheus receiver to scrape.

**How to leverage:**

- Automate updates to the JSON file from your infrastructure provisioning scripts (Terraform, Ansible, etc.)
- Each target gets labels (env, region, team) which become filterable dimensions in Grafana
- Works well when servers are provisioned manually but you want zero-downtime target updates


| Pros                                 | Cons                                                     |
| ------------------------------------ | -------------------------------------------------------- |
| No restart to add/remove servers     | Must switch from native receivers to prometheus receiver |
| Labels per target for rich filtering | You manage the targets file (still manual)               |
| Easy to automate via scripts         | Native redis receiver can't use file_sd                  |




---

**Approach 3: Service discovery (200+ servers, dynamic environments)**

The servers **announce themselves**. The collector doesn't need to be told about new servers — it asks Consul/Kubernetes "who's running right now?" and scrapes whatever answers.

```
New Redis server starts
       │
       ▼
Consul/Kubernetes  ◄── server registers itself on boot
       │
       ▼ collector polls every 30s
otel-collector  ──► "I see 47 Redis servers" ──► scrapes all 47
       │
       ▼
Next day: 3 servers die, 5 new ones start
       │
       ▼ collector polls again
otel-collector  ──► "I see 49 Redis servers" ──► automatically updated
```

**The key benefit:** Zero human intervention. Servers come and go — dashboards just reflect reality. On Kubernetes, you just add one annotation to your pod and the collector finds it automatically.

**How it works:**
Services register themselves in Consul (or Kubernetes annotations, or EC2 tags). The collector queries Consul/Kubernetes/EC2 API, gets the live list of targets, and scrapes them. When a server goes down or a new one comes up, the collector adapts within seconds.

```yaml
# otel-collector-config.yml
receivers:
  prometheus:
    config:
      scrape_configs:
        # Consul: discovers services tagged 'redis'
        - job_name: redis
          consul_sd_configs:
            - server: consul:8500
              services: ['redis']
          relabel_configs:
            - source_labels: [__meta_consul_tags]
              target_label: env

        # Kubernetes: discovers pods with annotation prometheus.io/scrape=true
        - job_name: nginx
          kubernetes_sd_configs:
            - role: pod
          relabel_configs:
            - source_labels: [__meta_kubernetes_pod_label_app]
              regex: nginx
              action: keep

        # AWS EC2: discovers instances with tag Role=nginx
        - job_name: nginx-ec2
          ec2_sd_configs:
            - region: us-east-1
              filters:
                - name: tag:Role
                  values: [nginx]
```

**How to leverage:**

- On Kubernetes: add annotation `prometheus.io/scrape: "true"` to your pod specs — collector picks them up automatically
- On AWS: tag your EC2 instances with `Role=redis` — collector discovers them via AWS API
- With Consul: services call `consul register` on startup — collector finds them within seconds


| Pros                                                    | Cons                                           |
| ------------------------------------------------------- | ---------------------------------------------- |
| Fully automatic, zero manual updates                    | Requires Consul/Kubernetes/EC2 already running |
| Scales to thousands of servers                          | High setup complexity                          |
| Industry standard for cloud-native                      | Overkill for small/medium setups               |
| Metadata (region, AZ, pod name) auto-attached as labels | Steep learning curve                           |




---

**Approach 4: Dedicated exporters (redis_exporter / nginx-prometheus-exporter)**

Instead of the collector talking directly to Redis/Nginx, a **specialist middleman** handles all the service-specific communication. The collector only talks to one place.

```
redis-1:6379 ──┐
redis-2:6379 ──┤
redis-3:6379 ──┼──► redis_exporter:9121 ◄── otel-collector ──► Grafana
...            │    (one process,            (scrapes ONE
redis-N:6379 ──┘     knows Redis deeply)      endpoint)
```

**The key benefit:** `redis_exporter` is purpose-built for Redis — it exposes 10x more metrics than the OTel native receiver. The collector doesn't need to know anything about Redis internals. Swap out the exporter, the rest of the pipeline stays the same.

```yaml
# otel-collector-config.yml
receivers:
  prometheus:
    config:
      scrape_configs:
        # scrape redis_exporter which internally monitors all Redis instances
        - job_name: redis
          static_configs:
            - targets: ['redis-exporter:9121']

        # scrape nginx-prometheus-exporter which monitors all Nginx instances
        - job_name: nginx
          static_configs:
            - targets: ['nginx-exporter:9113']

exporters:
  prometheusremotewrite:
    endpoint: http://prometheus:9090/api/v1/write

service:
  pipelines:
    metrics:
      receivers: [prometheus]
      processors: [batch, resourcedetection]
      exporters: [prometheusremotewrite]
```



```yaml
# docker-compose.yml additions
redis-exporter:
  image: oliver006/redis_exporter:latest
  # REDIS_ADDR accepts one address only — for multi-instance, use the multi-target
  # pattern: scrape /scrape?target=<redis-addr> with relabeling in otel-collector-config
  environment:
    - REDIS_ADDR=redis-1:6379
  ports:
    - "9121:9121"

nginx-exporter:
  image: nginx/nginx-prometheus-exporter:latest
  command:
    # double-dash required — nginx-prometheus-exporter uses Go flag syntax
    - --nginx.scrape-uri=http://nginx-1:80/status
    - --nginx.scrape-uri=http://nginx-2:80/status
  ports:
    - "9113:9113"
```


| Pros                                      | Cons                           |
| ----------------------------------------- | ------------------------------ |
| Richer metrics than OTel native receivers | One more process to run        |
| Battle-tested at production scale         | Extra layer of complexity      |
| Works with any scraper                    | Exporter itself can bottleneck |




---

**Approach 5: Multiple collector instances (1000+ servers)**

When one collector can't keep up with the volume, you run many collectors and split the work between them. A **Target Allocator** acts as a coordinator, ensuring no server is scraped twice or missed.

```
                    Target Allocator
                    (decides who scrapes what)
                    ┌──────────────────────┐
1000 servers ──────►│ collector-1: 1-333   │──► Prometheus
                    │ collector-2: 334-666 │──► Prometheus
                    │ collector-3: 667-1000│──► Prometheus
                    └──────────────────────┘
                    If collector-2 dies:
                    its targets are redistributed
                    to collector-1 and collector-3
```

**The key benefit:** Horizontal scalability and no single point of failure. If one collector crashes, its targets are automatically redistributed to the others. Used when you're at a scale where a single collector becomes a bottleneck.

```yaml
# OpenTelemetryCollector custom resource (deployed via OTel Operator on Kubernetes)
apiVersion: opentelemetry.io/v1beta1
kind: OpenTelemetryCollector
metadata:
  name: otel-collector
spec:
  mode: statefulset   # runs multiple collector replicas
  replicas: 3
  targetAllocator:
    enabled: true
    serviceAccount: otel-targetallocator
    prometheusCR:
      enabled: true   # reads Prometheus ServiceMonitor/PodMonitor CRDs
  config: |
    receivers:
      prometheus:
        config:
          scrape_configs:
            - job_name: redis
              kubernetes_sd_configs:
                - role: pod
              relabel_configs:
                - source_labels: [__meta_kubernetes_pod_label_app]
                  regex: redis
                  action: keep

    processors:
      batch:
      resourcedetection:
        detectors: [k8s_api, system]   # k8snode is deprecated, use k8s_api

    exporters:
      prometheusremotewrite:
        endpoint: http://prometheus:9090/api/v1/write

    service:
      pipelines:
        metrics:
          receivers: [prometheus]
          processors: [batch, resourcedetection]
          exporters: [prometheusremotewrite]
```


| Pros                          | Cons                             |
| ----------------------------- | -------------------------------- |
| Linear horizontal scalability | Needs Kubernetes + OTel Operator |
| No single point of failure    | Complex to coordinate            |




---



## 5. Decision guide

```
How many servers?
│
├── < 20, stable?          → Approach 1 (named instances)
├── 20–200?
│     ├── Have Consul/k8s? → Approach 3
│     └── No?              → Approach 2 (file_sd) or Approach 4 (dedicated exporter)
└── 200+?
      ├── On Kubernetes?   → Approach 3 + Approach 5
      └── Not on k8s?      → Approach 4 + Approach 2
```

---



## 6. Chosen scaling approach for this project

**Decision:** Approach 2 — File-based discovery.

**Why:** No Kubernetes or Consul setup available locally. Approach 2 requires no external infrastructure beyond Docker, fits within the scope of this project, and is a meaningful step up from Approach 1 — demonstrating dynamic target updates without a collector restart.

**Production recommendation:** Approach 3 + Approach 4 + Approach 5 together — the industry standard for production Kubernetes.

### Why Approach 3 + 5 complement each other

```
Kubernetes cluster
│
├── Pod comes up → registers itself automatically (Approach 3)
│
├── Target Allocator distributes targets across collectors (Approach 5)
│   ├── otel-collector-1 → scrapes pods 1–200
│   ├── otel-collector-2 → scrapes pods 201–400
│   └── otel-collector-3 → scrapes pods 401–600
│
└── If otel-collector-2 dies → targets redistributed automatically
```

- **Approach 3 alone** handles *discovery* — no manual config when pods scale up/down.
- **Approach 5 alone** handles *capacity* — one collector can't keep up with 500+ pods.
- **Together** they solve both problems: you never manually register a server AND you never hit a scraping bottleneck.



### In practice, a K8s production setup looks like this

1. Install the **OpenTelemetry Operator** in the cluster
2. Deploy an **OpenTelemetryCollector** custom resource (the Operator manages scaling)
3. Deploy a **Target Allocator** alongside it
4. Create a `PodMonitor` CRD for any service you want monitored:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: redis-monitor
spec:
  selector:
    matchLabels:
      app: redis
  podMetricsEndpoints:
    - port: metrics
```

That's the only thing an engineer needs to do to onboard a new service — the Target Allocator picks up the PodMonitor and distributes scraping automatically.

> **Note:** The `prometheus.io/scrape: "true"` annotation works with plain Kubernetes service discovery (Approach 3) but is **not** used by the Target Allocator in `prometheusCR` mode. The Target Allocator reads `PodMonitor` and `ServiceMonitor` CRDs instead.



### Where Approach 4 (dedicated exporters) still fits in K8s

For Redis and Nginx specifically, even in K8s, teams often run `redis_exporter` as a sidecar container alongside each Redis pod. It gives richer metrics than the OTel native receiver.

```
Redis pod
├── redis container        ← the actual database
└── redis_exporter sidecar ← exposes metrics for OTel collector to scrape
```

**The full production stack: Approach 3 + Approach 4 + Approach 5.**

---



## 7. Running the stack

```bash
# Generate mock metrics files first (required — mock-metrics/ and targets/ are not committed)
python3 generate_mock_metrics.py

# Start everything
docker compose up -d

# Check all containers are running
docker compose ps

# Watch collector logs (metrics print every 60s)
docker compose logs -f otel-collector

# Open Grafana
open http://localhost:3000   # admin / admin

# Open Prometheus
open http://localhost:9090
```

**Useful Grafana queries to start with:**

```
redis_memory_used
redis_clients_connected
nginx_connections_current
```

