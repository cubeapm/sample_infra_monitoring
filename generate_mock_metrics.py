import json
import random
import os

random.seed(42)  # deterministic — same values every run

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOCK_METRICS_DIR = os.path.join(BASE_DIR, "mock-metrics")
TARGETS_DIR = os.path.join(BASE_DIR, "targets")

os.makedirs(MOCK_METRICS_DIR, exist_ok=True)
os.makedirs(TARGETS_DIR, exist_ok=True)

ENVS = (
    ["prod"] * 20 +
    ["staging"] * 15 +
    ["dev"] * 15
)

REGIONS = (
    ["us-east"] * 10 +
    ["us-west"] * 10 +
    ["eu-west"] * 10 +
    ["ap-southeast"] * 10 +
    ["ap-northeast"] * 10
)


def nginx_metrics(i):
    active     = random.randint(50, 500)
    reading    = random.randint(1, 20)
    writing    = random.randint(5, 50)
    waiting    = max(0, active - reading - writing)
    requests   = random.randint(10_000, 1_000_000)
    accepted   = requests + random.randint(0, 1_000)
    handled    = accepted - random.randint(0, 200)

    return f"""\
# HELP nginx_connections_current Current nginx connections by state
# TYPE nginx_connections_current gauge
nginx_connections_current{{state="active"}} {active}
nginx_connections_current{{state="reading"}} {reading}
nginx_connections_current{{state="writing"}} {writing}
nginx_connections_current{{state="waiting"}} {waiting}
# HELP nginx_requests_total Total nginx requests
# TYPE nginx_requests_total counter
nginx_requests_total {requests}
# HELP nginx_connections_accepted_total Total accepted connections
# TYPE nginx_connections_accepted_total counter
nginx_connections_accepted_total {accepted}
# HELP nginx_connections_handled_total Total handled connections
# TYPE nginx_connections_handled_total counter
nginx_connections_handled_total {handled}
"""


def redis_metrics(i):
    memory_used        = random.randint(50_000_000, 2_000_000_000)
    memory_peak        = memory_used + random.randint(1_000_000, 100_000_000)
    clients_connected  = random.randint(1, 500)
    commands_processed = random.randint(100_000, 50_000_000)
    uptime             = random.randint(3_600, 2_592_000)
    hits               = random.randint(10_000, 5_000_000)
    misses             = random.randint(100, 100_000)
    net_input          = random.randint(1_000_000, 1_000_000_000)
    net_output         = random.randint(1_000_000, 2_000_000_000)
    rdb_changes        = random.randint(0, 10_000)
    connected_slaves   = random.randint(0, 3)

    return f"""\
# HELP redis_memory_used Memory used by Redis in bytes
# TYPE redis_memory_used gauge
redis_memory_used {memory_used}
# HELP redis_memory_peak Peak memory used by Redis in bytes
# TYPE redis_memory_peak gauge
redis_memory_peak {memory_peak}
# HELP redis_clients_connected Number of connected clients
# TYPE redis_clients_connected gauge
redis_clients_connected {clients_connected}
# HELP redis_commands_processed_total Total commands processed
# TYPE redis_commands_processed_total counter
redis_commands_processed_total {commands_processed}
# HELP redis_uptime_in_seconds Uptime in seconds
# TYPE redis_uptime_in_seconds counter
redis_uptime_in_seconds {uptime}
# HELP redis_keyspace_hits_total Total keyspace hits
# TYPE redis_keyspace_hits_total counter
redis_keyspace_hits_total {hits}
# HELP redis_keyspace_misses_total Total keyspace misses
# TYPE redis_keyspace_misses_total counter
redis_keyspace_misses_total {misses}
# HELP redis_net_input_bytes_total Total net input bytes
# TYPE redis_net_input_bytes_total counter
redis_net_input_bytes_total {net_input}
# HELP redis_net_output_bytes_total Total net output bytes
# TYPE redis_net_output_bytes_total counter
redis_net_output_bytes_total {net_output}
# HELP redis_rdb_changes_since_last_save RDB changes since last save
# TYPE redis_rdb_changes_since_last_save gauge
redis_rdb_changes_since_last_save {rdb_changes}
# HELP redis_connected_slaves Number of connected slaves
# TYPE redis_connected_slaves gauge
redis_connected_slaves {connected_slaves}
"""


nginx_targets = []
redis_targets = []

for i in range(1, 51):
    env    = ENVS[i - 1]
    region = REGIONS[i - 1]

    # nginx
    with open(f"{MOCK_METRICS_DIR}/nginx-{i}.txt", "w") as f:
        f.write(nginx_metrics(i))
    nginx_targets.append({
        "targets": ["fake-metrics-server:80"],
        "labels": {
            "__metrics_path__": f"/metrics/nginx-{i}.txt",
            "server": f"nginx-{i}",
            "env": env,
            "region": region,
            "service": "nginx"
        }
    })

    # redis
    with open(f"{MOCK_METRICS_DIR}/redis-{i}.txt", "w") as f:
        f.write(redis_metrics(i))
    redis_targets.append({
        "targets": ["fake-metrics-server:80"],
        "labels": {
            "__metrics_path__": f"/metrics/redis-{i}.txt",
            "server": f"redis-{i}",
            "env": env,
            "region": region,
            "service": "redis"
        }
    })

with open(f"{TARGETS_DIR}/nginx-targets.json", "w") as f:
    json.dump(nginx_targets, f, indent=2)

with open(f"{TARGETS_DIR}/redis-targets.json", "w") as f:
    json.dump(redis_targets, f, indent=2)

print(f"Generated {len(nginx_targets)} nginx + {len(redis_targets)} redis fake metrics files")
print(f"Generated {TARGETS_DIR}/nginx-targets.json and {TARGETS_DIR}/redis-targets.json")
print("\nDistribution:")
for env in ["prod", "staging", "dev"]:
    count = sum(1 for t in nginx_targets if t["labels"]["env"] == env)
    print(f"  {env}: {count} servers")
print()
for region in ["us-east", "us-west", "eu-west", "ap-southeast", "ap-northeast"]:
    count = sum(1 for t in nginx_targets if t["labels"]["region"] == region)
    print(f"  {region}: {count} servers")
