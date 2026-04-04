def replace(path: str, value):
    return {
        "op": "replace",
        "path": path,
        "value": value,
    }
