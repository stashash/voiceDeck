"""Durable source evidence independent of themes, model wording and deck layout."""
from __future__ import annotations

import base64
import hashlib

from designer import store
from designer.insights.table import Table, file_name


def persist_source(data: bytes, filename: str, table_index: int, table: Table) -> tuple[str, str]:
    digest = hashlib.sha256(data).hexdigest()
    snapshot = {
        "version": 1,
        "file_name": file_name(filename),
        "source_sha256": digest,
        "size_bytes": len(data),
        "source_base64": base64.b64encode(data).decode("ascii"),
        "table_index": table_index,
        "table": {"name": table.name, "sheet": table.sheet, "headers": table.headers,
                  "rows": table.rows, "row_lines": table.lines, "from_image": table.from_image},
    }
    return store.save_dataset(snapshot), digest
