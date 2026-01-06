import os
import random
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests


def getenv_int(name: str, default: int) -> int:
    val = os.getenv(name, "")
    if val == "" or val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def getenv_float(name: str, default: float) -> float:
    val = os.getenv(name, "")
    if val == "" or val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


CONTROLLER_URL = os.getenv("CONTROLLER_URL") or "http://iot-controller:8000"
SEND_INTERVAL = getenv_float("SEND_INTERVAL", 1.0)
REFRESH_DEVICES_EVERY = getenv_int("SIM_REFRESH_INTERVAL", 10)
AUTH_EMAIL = os.getenv("SIM_AUTH_EMAIL") or "senya@example.com"
AUTH_PASSWORD = os.getenv("SIM_AUTH_PASSWORD") or "senya123"


def gen_payload(device_id: str, seq: int):
    return {
        "device_id": str(device_id),
        "ts": datetime.now(timezone.utc).isoformat(),
        "field_a": round(random.uniform(0, 10), 3),
        "field_b": round(random.uniform(0, 10), 3),
        "battery": random.randint(20, 100),
        "seq": seq,
        "meta": {"fw": "1.0.0", "net": random.choice(["wifi", "lte"])},
    }


def auth_token() -> Optional[str]:
    try:
        resp = requests.post(
            f"{CONTROLLER_URL}/auth/login",
            json={"email": AUTH_EMAIL, "password": AUTH_PASSWORD},
            timeout=5,
        )
        if resp.status_code != 200:
            print(f"[AUTH] failed {resp.status_code}: {resp.text}")
            return None
        return resp.json().get("token")
    except Exception as exc:
        print(f"[AUTH] error: {exc}")
        return None


def fetch_devices(token: str) -> List[Dict]:
    try:
        resp = requests.get(
            f"{CONTROLLER_URL}/devices",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if resp.status_code != 200:
            print(f"[DEVICES] failed {resp.status_code}: {resp.text}")
            return []
        return resp.json()
    except Exception as exc:
        print(f"[DEVICES] error: {exc}")
        return []


def main():
    token = auth_token()
    devices: List[Dict] = []
    seqs: Dict[str, int] = {}
    last_refresh = 0

    print(
        f"Simulator starting interval {SEND_INTERVAL}s, controller {CONTROLLER_URL}, auth {AUTH_EMAIL}"
    )
    while True:
        now = time.time()
        if token and (now - last_refresh > REFRESH_DEVICES_EVERY):
            devices = fetch_devices(token)
            last_refresh = now
            for d in devices:
                dev_id = str(d.get("_id") or d.get("external_id"))
                if dev_id not in seqs:
                    seqs[dev_id] = 0

        if not devices:
            time.sleep(SEND_INTERVAL)
            continue

        for dev in devices:
            dev_id = str(dev.get("_id") or dev.get("external_id"))
            if not dev_id:
                continue
            seqs[dev_id] = seqs.get(dev_id, 0) + 1
            payload = gen_payload(dev_id, seqs[dev_id])
            try:
                resp = requests.post(f"{CONTROLLER_URL}/ingest", json=payload, timeout=5)
                if resp.status_code >= 300:
                    print(f"[WARN] device {dev_id} status {resp.status_code}: {resp.text}")
            except Exception as exc:
                print(f"[ERROR] device {dev_id}: {exc}")

        time.sleep(SEND_INTERVAL)


if __name__ == "__main__":
    main()
