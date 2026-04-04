class SchemaViolation(Exception):
    pass


class SchemaGuard:

    def __init__(self, freezer, alert_cb):
        self.freezer = freezer
        self.alert_cb = alert_cb

    def guard(self, source: str, raw_msg, fn):
        try:
            return fn(raw_msg)
        except Exception as e:
            reason = f"{source} schema violation: {e}"
            self.freezer.freeze(reason)
            self.alert_cb(reason, raw_msg)
            raise SchemaViolation(reason)
