# Simple IoT Service (Flask + Docker Compose)

Учебный проект: простой IoT-поток с контроллером (Flask), rule engine, симулятором данных, брокером RabbitMQ, хранилищем сообщений в MongoDB и алёртов в Postgres, с метриками (Prometheus/Grafana) и логами (ELK). UI — React/Vite.

## Компоненты
- IoT Controller (Flask): принимает HTTP POST `/ingest`, валидирует JSON, пишет в MongoDB `iot.messages`, публикует в RabbitMQ exchange `iot.msg`.
- Rule Engine: читает очередь `iot.rules`, проверяет мгновенные и длящиеся правила (10 подряд пакетов), сохраняет алёрты в Postgres `alerts`.
- Data Simulator: генерирует 15 устройств, 1 msg/сек/устройство, шлёт в контроллер.
- MongoDB: хранилище пакетов.
- RabbitMQ: обмен `iot.msg`, очередь `iot.rules`.
- Postgres: таблица `alerts` (jsonb payload, индексы по `device_id`, `triggered_at`).
- Metrics: Prometheus + exporters (Python, rabbit/mongo/postgres); Grafana дашборды.
- Logs: структурированные JSON → Filebeat/Fluent Bit → Elasticsearch; Kibana для просмотра.
- UI: React/Vite панель последних пакетов, алёртов, статуса; Compass для Mongo просмотра.

## Архитектура
- Поток: Simulator → Controller → Mongo + RabbitMQ → Rule Engine → Postgres (алёрты).
- Схема сообщения: `device_id` (str), `ts` (ISO8601), `field_a` (float), `field_b` (float), `battery` (0–100), `seq` (int), `meta` (obj, опц.).
- Правила: мгновенное `field_a > 5` для `device_id=42`; длящееся — то же условие 10 подряд пакетов.
- Подробности и диаграмма — `docs/architecture.md`.

## План работ (15 шагов)
См. `docs/plan.md` — шаги от архитектуры до презентации PDF, выполняем по очереди с вашей отмашки.

## Статус
- Этап 1: архитектура и схемы — задокументировано.
- Далее: scaffolding репозитория и docker-compose каркас (после подтверждения).
