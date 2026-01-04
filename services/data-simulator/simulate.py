import json
import os
import random
import time
from datetime import datetime, timezone

import requests


CONTROLLER_URL = os.getenv("CONTROLLER_URL", "http://iot-controller:8000")
DEVICES_COUNT = int(os.getenv("DEVICES_COUNT", "15"))
SEND_INTERVAL = float(os.getenv("SEND_INTERVAL", "1"))


def gen_payload(device_id: int, seq: int):
    return {
        "device_id": str(device_id),
        "ts": datetime.now(timezone.utc).isoformat(),
        "field_a": round(random.uniform(0, 10), 3),
        "field_b": round(random.uniform(0, 10), 3),
        "battery": random.randint(20, 100),
        "seq": seq,
        "meta": {"fw": "1.0.0", "net": random.choice(["wifi", "lte"])},
    }


def main():
    seqs = {i: 0 for i in range(1, DEVICES_COUNT + 1)}
    print(f"Simulator starting for {DEVICES_COUNT} devices, interval {SEND_INTERVAL}s, controller {CONTROLLER_URL}")
    while True:
        for device_id in seqs:
            seqs[device_id] += 1
            payload = gen_payload(device_id, seqs[device_id])
            try:
                resp = requests.post(f"{CONTROLLER_URL}/ingest", json=payload, timeout=5)
                if resp.status_code >= 300:
                    print(f"[WARN] device {device_id} status {resp.status_code}: {resp.text}")
            except Exception as exc:
                print(f"[ERROR] device {device_id}: {exc}")
        time.sleep(SEND_INTERVAL)


if __name__ == "__main__":
    main()
