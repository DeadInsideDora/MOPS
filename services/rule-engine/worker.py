import json
import os
import time
from typing import Dict, Any

import pika
import psycopg
from prometheus_client import Counter, Histogram, start_http_server


RABBITMQ_URL = os.getenv("RABBITMQ_URL") or "amqp://guest:guest@rabbitmq:5672/"
POSTGRES_DSN = os.getenv("POSTGRES_DSN") or "postgresql://iot:iot@postgres:5432/iot"
METRICS_PORT = int(os.getenv("PROMETHEUS_PORT", "9001") or "9001")

exchange_name = "iot.msg"
queue_name = "iot.rules"

rule_instant_device = "42"
rule_instant_threshold = 5.0
rule_persistent_count = 10

rule_hits = Counter("rule_engine_hits_total", "Rule hits", ["rule_id"])
rule_processed = Counter("rule_engine_processed_total", "Messages processed")
rule_errors = Counter("rule_engine_errors_total", "Processing errors")
rule_latency = Histogram("rule_engine_process_seconds", "Processing latency seconds")


def ensure_db(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                device_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                rule_type TEXT NOT NULL CHECK (rule_type IN ('instant', 'persistent')),
                triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                payload JSONB NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                severity INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS alerts_device_ts_idx ON alerts (device_id, triggered_at DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS alerts_rule_idx ON alerts (rule_id);")
    conn.commit()


def handle_message(body: bytes, state: Dict[str, int], pg_conn) -> None:
    payload: Dict[str, Any] = json.loads(body.decode("utf-8"))
    device_id = str(payload.get("device_id"))
    field_a = float(payload.get("field_a", 0))

    rule_processed.inc()
    if device_id == rule_instant_device and field_a > rule_instant_threshold:
        rule_id = "instant_42_a_gt_5"
        rule_hits.labels(rule_id=rule_id).inc()
        insert_alert(pg_conn, device_id, rule_id, "instant", payload, 1, severity=1)

    if device_id == rule_instant_device and field_a > rule_instant_threshold:
        state[device_id] = state.get(device_id, 0) + 1
    else:
        state[device_id] = 0

    if state.get(device_id, 0) >= rule_persistent_count:
        rule_id = "persistent_42_a_gt_5"
        rule_hits.labels(rule_id=rule_id).inc()
        insert_alert(
            pg_conn,
            device_id,
            rule_id,
            "persistent",
            payload,
            count=state[device_id],
            severity=2,
        )
        state[device_id] = 0


def insert_alert(conn, device_id: str, rule_id: str, rule_type: str, payload: Dict[str, Any], count: int, severity: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO alerts (device_id, rule_id, rule_type, payload, count, severity)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s)
            """,
            (device_id, rule_id, rule_type, json.dumps(payload), count, severity),
        )
    conn.commit()


def main():
    start_http_server(METRICS_PORT)

    pg_conn = psycopg.connect(POSTGRES_DSN)
    ensure_db(pg_conn)

    params = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.exchange_declare(exchange=exchange_name, exchange_type="topic", durable=True)
    channel.queue_declare(queue=queue_name, durable=True)
    channel.queue_bind(queue=queue_name, exchange=exchange_name, routing_key="device.*")

    state: Dict[str, int] = {}

    def callback(ch, method, properties, body):
        start = time.time()
        try:
            handle_message(body, state, pg_conn)
        except Exception:
            rule_errors.inc()
        finally:
            rule_latency.observe(time.time() - start)
            ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_qos(prefetch_count=10)
    channel.basic_consume(queue=queue_name, on_message_callback=callback)

    print("Rule engine started")
    channel.start_consuming()


if __name__ == "__main__":
    main()
