# Sample Infra Monitoring

This is a sample project to demonstrate how to ingest infra metrics into CubeAPM using OpenTelemetry Collector. It collects metrics from various sources and feeds them into CubeAPM. This repository has a docker compose file to set up all these services conveniently.

## Setup

Clone this repository and go to the project directory. Then run the following commands

```
docker compose up --build
```

## Notes

1. Detailed documentation for each infra component is available at https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver.

1. To get Kafka metrics, you need to create a topic and produce some messages. Open Kafdrop at http://localhost:19000 and create a topic named `mytopic`. Then run the following command to produce messages to the topic:

   ```bash
   docker exec -it infra_monitoring-kafka-1 kafka-console-producer --broker-list localhost:9092 --topic mytopic
   ```

   The producer will wait for input. You can you can enter one message per line and finalize the input by pressing `Ctrl+D`. This will produce messages to the topic.

1. RabbitMQ metrics are scraped from its built-in Prometheus plugin (enabled automatically, exposed at http://localhost:15692/metrics). The `rabbitmq-loadgen` service (RabbitMQ `perf-test`) continuously publishes/consumes messages on a `demo-queue` so connection, channel, queue and message-rate metrics stay non-zero. You can also inspect the broker directly via the management UI at http://localhost:15672 (login YOUR_USERNAME/YOUR_PASSWORD). Metrics tied to unused features (quorum/stream queues, federation, shovels, TLS, LDAP) stay at 0 unless you exercise those features.

## Contributing

Please feel free to raise PR for any enhancements - additional integrations, version updates, documentation updates, etc.
