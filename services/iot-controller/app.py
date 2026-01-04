import os
import json
import time
from datetime import datetime
from typing import Any, Dict

from flask import Flask, request, jsonify
from pymongo import MongoClient
import pika
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST


def create_app() -> Flask:
    app = Flask(__name__)

    mongo_uri = os.getenv("MONGO_URI", "mongodb://mongo:27017/iot")
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")

    mongo_client = MongoClient(mongo_uri)
    mongo_db = mongo_client.get_default_database()
    messages = mongo_db.messages

    params = pika.URLParameters(rabbitmq_url)
    rabbit_conn = pika.BlockingConnection(params)
    channel = rabbit_conn.channel()
    exchange_name = "iot.msg"
    channel.exchange_declare(exchange=exchange_name, exchange_type="topic", durable=True)

    req_count = Counter("iot_controller_requests_total", "Total ingest requests")
    req_fail = Counter("iot_controller_requests_failed_total", "Failed ingest requests")
    validation_fail = Counter("iot_controller_validation_failed_total", "Invalid payloads")
    mongo_fail = Counter("iot_controller_mongo_failed_total", "Mongo write failures")
    rabbit_fail = Counter("iot_controller_rabbit_failed_total", "Rabbit publish failures")
    req_latency = Histogram("iot_controller_request_seconds", "Ingest request latency seconds")

    def validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        required = ["device_id", "ts", "field_a", "field_b", "battery", "seq"]
        if not all(k in payload for k in required):
            raise ValueError("missing required fields")
        payload["device_id"] = str(payload["device_id"])
        payload["ts"] = str(payload["ts"])
        payload["field_a"] = float(payload["field_a"])
        payload["field_b"] = float(payload["field_b"])
        payload["battery"] = int(payload["battery"])
        payload["seq"] = int(payload["seq"])
        payload.setdefault("meta", {})
        return payload

    @app.route("/ingest", methods=["POST"])
    def ingest():
        start = time.time()
        req_count.inc()
        try:
            payload = request.get_json(force=True, silent=False)
        except Exception:
            req_fail.inc()
            return jsonify({"error": "invalid json"}), 400
        try:
            validated = validate_payload(payload)
        except Exception as exc:
            validation_fail.inc()
            req_fail.inc()
            return jsonify({"error": str(exc)}), 400
        try:
            messages.insert_one(validated)
        except Exception as exc:
            mongo_fail.inc()
            req_fail.inc()
            return jsonify({"error": "db_error", "details": str(exc)}), 500
        try:
            routing_key = f"device.{validated['device_id']}"
            channel.basic_publish(
                exchange=exchange_name,
                routing_key=routing_key,
                body=json.dumps(validated).encode("utf-8"),
                properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
            )
        except Exception as exc:
            rabbit_fail.inc()
            req_fail.inc()
            return jsonify({"error": "rabbit_error", "details": str(exc)}), 500
        finally:
            req_latency.observe(time.time() - start)
        return jsonify({"status": "ok"}), 200

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()}), 200

    @app.route("/metrics")
    def metrics():
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

    return app


app = create_app()
