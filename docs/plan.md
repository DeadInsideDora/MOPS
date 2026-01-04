# План из 15 этапов

1) Архитектура: формат сообщений, очередь, коллекции/таблицы, события алёртов (готово).  
2) Репо-скелет: папки services/ui/infra/docs, базовый README/Makefile заготовки.  
3) Docker Compose каркас: сервисы (controller, rule-engine, simulator, mongo, rabbitmq, postgres, grafana, elastic+kibana, prometheus+exporters), сети/volumes.  
4) Схемы данных: Mongo коллекция/индексы, Postgres `alerts` DDL, env образцы.  
5) Flask IoT controller: `/ingest` валидация JSON, запись в Mongo, publish в RabbitMQ, healthcheck.  
6) Rule engine worker: consume из очереди, мгновенные/длящиеся правила (10 пакетов), запись алёртов в Postgres.  
7) Data simulator: 15 устройств, 1 msg/сек, конфигурируемая частота/число устройств.  
8) Метрики: Prometheus client в Python, rabbit/mongo/postgres exporters, базовые метрики потоков.  
9) Логи: структурированные JSON, Filebeat/Fluent Bit в Elasticsearch, базовые Kibana dashboards.  
10) UI: React/Vite фронт для пакетов/алёртов/статусов, вызов симулятора.  
11) Grafana: дашборды по метрикам потока, задержкам, алёртам.  
12) Тесты: интеграционные для controller (Mongo+Rabbit) и rule engine (Rabbit+Postgres).  
13) Документация запуска: инструкции docker compose, примеры curl, env.  
14) Финальная проверка: прогон compose, smoke-тесты, метрики/логи/UI доступность.  
15) Презентация PDF: архитектура, пайплайны, метрики/логи, выводы.
