"""Codex http_headers_helper. Stdout is consumed by Codex, not a human log."""
import json
from credentials import load_token

if __name__ == "__main__":
    print(json.dumps({"Authorization": "Bearer " + load_token()}))
