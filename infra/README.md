# Infra layout

- Docker Compose манифесты и env.
- Конфиги для Prometheus/Grafana, Filebeat/Fluent Bit, Elasticsearch/Kibana, exporters.
- DDL для Postgres (alerts).

Сейчас добавлено:
- `docker-compose.yml` — каркас сервисов.
- `prometheus/prometheus.yml` — базовый scrape (будет расширен).
- `fluent-bit/fluent-bit.conf` — черновик вывода в Elasticsearch.
- `postgres/init.sql` — таблица `alerts` с индексами.
- `mongo/init.js` — индексы для `iot.messages`.
