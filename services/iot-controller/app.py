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

    mongo_uri = os.getenv("MONGO_URI") or "mongodb://mongo:27017/iot"
    rabbitmq_url = os.getenv("RABBITMQ_URL") or "amqp://guest:guest@rabbitmq:5672/"

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

    @app.route("/messages", methods=["GET"])
    def list_messages():
        """
        Возвращает последние сообщения. Поддерживает фильтр по device_id и лимит.
        GET /messages?device_id=42&limit=50
        """
        device_id = request.args.get("device_id")
        try:
            limit = int(request.args.get("limit", "100"))
            limit = min(max(limit, 1), 500)
        except ValueError:
            return jsonify({"error": "limit must be int"}), 400

        query = {}
        if device_id:
            query["device_id"] = str(device_id)
        docs = (
            messages.find(query).sort("ts", -1).limit(limit)
        )
        return jsonify([serialize_doc(d) for d in docs]), 200

    @app.route("/stats", methods=["GET"])
    def stats():
        """
        Быстрые агрегаты: количество сообщений и последние по device_id.
        """
        total = messages.estimated_document_count()
        latest_cursor = messages.find().sort("ts", -1).limit(1)
        latest_item = next(latest_cursor, None)
        latest_doc = serialize_doc(latest_item) if latest_item else None
        return jsonify({"messages_total": total, "latest": latest_doc}), 200

    @app.route("/metrics")
    def metrics():
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

    return app


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


app = create_app()
