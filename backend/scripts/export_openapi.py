"""Print the API's OpenAPI schema, the source the frontend's types are generated from.

Run from backend/ as `uv run python -m scripts.export_openapi` (see `make fe-types`). No
server, DB, or `local` extra needed: importing the app only builds the route table.
"""

import json

from app.main import app

print(json.dumps(app.openapi(), indent=2, sort_keys=True))
