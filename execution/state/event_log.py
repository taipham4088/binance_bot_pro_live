import json
import time
from pathlib import Path

LOG_FILE = Path("data/events.log")


class EventLogger:

    def log(self, event_type: str, payload):
        LOG_FILE.parent.mkdir(exist_ok=True)
        record = {
            "ts": time.time(),
            "type": event_type,
            "data": payload
        }
        with LOG_FILE.open("a", encoding="utf8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
