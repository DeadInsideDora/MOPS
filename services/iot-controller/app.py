import os
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from flask import Flask, request, jsonify, g
from flask_cors import CORS
from pymongo import MongoClient
import pika
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import jwt
from werkzeug.security import generate_password_hash, check_password_hash


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    mongo_uri = os.getenv("MONGO_URI") or "mongodb://mongo:27017/iot"
    rabbitmq_url = os.getenv("RABBITMQ_URL") or "amqp://guest:guest@rabbitmq:5672/"
    jwt_secret = os.getenv("JWT_SECRET") or "dev-secret"

    def connect_mongo(uri: str, retries: int = 10, delay: float = 2.0):
        last_exc = None
        for _ in range(retries):
            try:
                client = MongoClient(uri, serverSelectionTimeoutMS=2000)
                client.admin.command("ping")
                return client
            except Exception as exc:
                last_exc = exc
                time.sleep(delay)
        raise last_exc

    def connect_rabbit(url: str, retries: int = 10, delay: float = 2.0):
        last_exc = None
        for _ in range(retries):
            try:
                params = pika.URLParameters(url)
                conn = pika.BlockingConnection(params)
                return conn
            except Exception as exc:
                last_exc = exc
                time.sleep(delay)
        raise last_exc

    mongo_client = connect_mongo(mongo_uri)
    mongo_db = mongo_client.get_default_database()
    messages = mongo_db.messages
    users = mongo_db.users
    devices = mongo_db.devices

    rabbit_conn = connect_rabbit(rabbitmq_url)
    channel = rabbit_conn.channel()
    exchange_name = "iot.msg"
    channel.exchange_declare(exchange=exchange_name, exchange_type="topic", durable=True)

    req_count = Counter("iot_controller_requests_total", "Total ingest requests")
    req_fail = Counter("iot_controller_requests_failed_total", "Failed ingest requests")
    validation_fail = Counter("iot_controller_validation_failed_total", "Invalid payloads")
    mongo_fail = Counter("iot_controller_mongo_failed_total", "Mongo write failures")
    rabbit_fail = Counter("iot_controller_rabbit_failed_total", "Rabbit publish failures")
    req_latency = Histogram("iot_controller_request_seconds", "Ingest request latency seconds")

    def create_token(user: Dict[str, Any]) -> str:
        payload = {
            "sub": str(user["_id"]),
            "email": user["email"],
            "exp": datetime.utcnow() + timedelta(days=7),
        }
        return jwt.encode(payload, jwt_secret, algorithm="HS256")

    def decode_token(token: str) -> Optional[Dict[str, Any]]:
        try:
            return jwt.decode(token, jwt_secret, algorithms=["HS256"])
        except Exception:
            return None

    def require_auth():
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ", 1)[1].strip()
        data = decode_token(token)
        if not data:
            return None
        user = users.find_one({"_id": data["sub"]}) or users.find_one({"_id": str(data["sub"])})
        if user:
            g.user = user
        return user

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

    @app.route("/auth/register", methods=["POST"])
    def register():
        data = request.get_json(force=True, silent=True) or {}
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", "")).strip()
        if not email or not password:
            return jsonify({"error": "email and password required"}), 400
        if users.find_one({"email": email}):
            return jsonify({"error": "user_exists"}), 409
        user_id = str(uuid.uuid4())
        users.insert_one(
            {
                "_id": user_id,
                "email": email,
                "password_hash": generate_password_hash(password),
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        token = create_token({"_id": user_id, "email": email})
        return jsonify({"token": token, "email": email}), 201

    @app.route("/auth/login", methods=["POST"])
    def login():
        data = request.get_json(force=True, silent=True) or {}
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", "")).strip()
        user = users.find_one({"email": email})
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "invalid_credentials"}), 401
        token = create_token(user)
        return jsonify({"token": token, "email": user["email"]}), 200

    @app.route("/me", methods=["GET"])
    def me():
        user = require_auth()
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        return jsonify({"email": user["email"]}), 200

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
            doc = dict(validated)
            messages.insert_one(doc)
        except Exception as exc:
            mongo_fail.inc()
            req_fail.inc()
            return jsonify({"error": "db_error", "details": str(exc)}), 500
        try:
            routing_key = f"device.{validated['device_id']}"
            channel.basic_publish(
                exchange=exchange_name,
                routing_key=routing_key,
                body=json.dumps({k: v for k, v in doc.items() if k != "_id"}).encode("utf-8"),
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

    @app.route("/devices", methods=["GET", "POST"])
    def devices_collection():
        user = require_auth()
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        if request.method == "GET":
            docs = devices.find().sort("created_at", -1)
            return jsonify([serialize_doc(d) for d in docs]), 200
        # POST
        data = request.get_json(force=True, silent=True) or {}
        name = str(data.get("name", "")).strip()
        description = str(data.get("description", "")).strip()
        external_id = str(data.get("external_id", "")).strip() or None
        if not name:
            return jsonify({"error": "name_required"}), 400
        device = {
            "_id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "external_id": external_id,
            "created_at": datetime.utcnow().isoformat(),
            "created_by": user["email"],
        }
        devices.insert_one(device)
        return jsonify(serialize_doc(device)), 201

    @app.route("/devices/<device_id>", methods=["GET", "PUT", "DELETE"])
    def device_item(device_id: str):
        user = require_auth()
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        existing = devices.find_one({"_id": device_id})
        if not existing:
            return jsonify({"error": "not_found"}), 404
        if request.method == "GET":
            return jsonify(serialize_doc(existing)), 200
        if request.method == "DELETE":
            devices.delete_one({"_id": device_id})
            return jsonify({"status": "deleted"}), 200
        # PUT
        data = request.get_json(force=True, silent=True) or {}
        updates: Dict[str, Any] = {}
        if "name" in data:
            updates["name"] = str(data["name"]).strip()
        if "description" in data:
            updates["description"] = str(data["description"]).strip()
        if "external_id" in data:
            val = str(data["external_id"]).strip()
            updates["external_id"] = val or None
        if updates:
            devices.update_one({"_id": device_id}, {"$set": updates})
        new_doc = devices.find_one({"_id": device_id})
        return jsonify(serialize_doc(new_doc)), 200

    @app.route("/metrics")
    def metrics():
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

    return app


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


app = create_app()
