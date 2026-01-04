# Архитектура и схемы

## Диаграмма (концепт)
```mermaid
graph LR
    DS[Data simulator] -->|HTTP /ingest| CTRL[IoT Controller (Flask)]
    CTRL -->|write| MONGO[MongoDB iot.messages]
    CTRL -->|publish| MQ[(RabbitMQ exchange iot.msg)]
    MQ -->|queue iot.rules| RE[Rule engine]
    RE -->|alerts| PG[(Postgres alerts)]
    CTRL -. logs/metrics .-> ELK[(ELK)]
    RE -. logs/metrics .-> ELK
    CTRL -. metrics .-> PROMO[(Prometheus/Grafana)]
    RE -. metrics .-> PROMO
    MONGO -. metrics .-> PROMO
    MQ -. metrics .-> PROMO
    MONGO <-- Compass
```

## Поток данных
1. Simulator генерирует сообщения (15 устройств, 1 msg/сек/устройство) и шлёт HTTP POST `/ingest`.
2. IoT Controller валидирует JSON, пишет документ в MongoDB `iot.messages`, публикует в RabbitMQ exchange `iot.msg` (topic, routing key `device.<device_id>`).
3. Rule Engine читает очередь `iot.rules` (bound на `iot.msg`), держит state per `device_id`.
4. При срабатывании правила пишет запись в Postgres `alerts` и при необходимости дублирует в Mongo (опц).
5. Логи сервисов уходят в stdout → Filebeat/Fluent Bit → Elasticsearch → Kibana. Метрики собирает Prometheus, Grafana дашборды.

## Формат сообщения устройства
```json
{
  "device_id": "string",
  "ts": "ISO8601 string",
  "field_a": 0.0,
  "field_b": 0.0,
  "battery": 95,
  "seq": 123,
  "meta": {
    "fw": "1.0.0",
    "net": "wifi"
  }
}
```
- Обязательные: `device_id`, `ts`, `field_a`, `field_b`, `battery`, `seq`.
- `meta` опционален, для расширений.

## Правила
- Мгновенное: `device_id = 42` и `field_a > 5`.
- Длящееся: то же условие 10 подряд пакетов от `device_id = 42`.
- State для длящегося правила хранится в памяти Rule Engine (скользящее окно/счётчик подряд).

## Очереди и маршрутизация
- Exchange: `iot.msg` (topic).
- Routing key: `device.<device_id>`.
- Queue: `iot.rules`, binding `device.*`.

## Базы данных
### MongoDB
- База: `iot`.
- Коллекция: `messages`.
- Индексы: `device_id`, `ts`, композит `device_id+ts` для сортировки по времени.

### Postgres (алёрты)
- Таблица `alerts`:
  - `id` UUID PK
  - `device_id` text
  - `rule_id` text (e.g. `instant_42_a_gt_5`, `persist_42_a_gt_5`)
  - `rule_type` text check (`instant`/`persistent`)
  - `triggered_at` timestamptz default now()
  - `payload` jsonb (последний пакет или окно)
  - `count` int (для длящегося — сколько подряд)
  - `severity` int default 1
- Индексы: `device_id, triggered_at desc`; `rule_id`.

## Метрики
- Python services: `prometheus_client` (req durations, validations, rule hits, queue lag/consume latency).
- Exporters: RabbitMQ, MongoDB, Postgres (официальные образцы/экспортеры).
- Grafana: панели потока сообщений, ошибок валидации, latency ingest→alert, загрузка брокера/БД.

## Логи
- Структурированные JSON в stdout (controller, rule engine, simulator).
- Filebeat/Fluent Bit собирает и шипит в Elasticsearch индекс `iot-logs-*`.
- Kibana для поиска/фильтрации по `device_id`, `rule_id`, уровню, трассировкам запросов.

## UI
- React/Vite SPA, общается с backend API (Flask или маленький proxy):
  - Лента последних пакетов (Mongo tail/limit).
  - Лента алёртов (Postgres).
  - Статус сервисов/метрик (Prometheus/Grafana links).
  - Кнопка запуска/настройки симуляции (кол-во устройств, частота).

## Окружение и сети
- Docker Compose, две сети: `backend` (сервисы+БД) и `frontend` (UI/Grafana/Kibana).
- Конфигурация через `.env` с дефолтами для портов, кредов БД/брокера.

## Предпосылки для тестов
- Интеграционные тесты:
  - Controller: POST → проверка записи в Mongo и publish в RabbitMQ (mock/fake broker).
  - Rule Engine: consume тестовый пакет → алёрт в Postgres, проверка длящегося окна.
