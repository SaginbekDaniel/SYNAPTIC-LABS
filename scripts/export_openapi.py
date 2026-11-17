"""Write the API's OpenAPI document so the web client types can be regenerated and diffed."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from nexora.api.main import create_app

out = Path(sys.argv[1] if len(sys.argv) > 1 else "apps/web/openapi.json")
out.write_text(json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {out}")
