# JSON I/O audit allowlist

Direct JSON writes outside `RunContext.write_json` are allowed only for operational paths listed in `tools/audit_json_io.py` `ALLOWLIST`.

**Canonical write path:** `RunContext.write_json` → schema validation → `file_store.write_json`.

**Canonical read path:** `RunContext.read_json` / `read_path` → `resolve_read_path` (staged → committed).

**Fixed (Track A0):** `GET /api/runs/{id}/artifact` uses `read_path` / `resolve_read_path`.

**Fixed (Track B5):** `nle_state.save_nle` uses `ctx.write_json`.

Run audit: `python tools/audit_json_io.py`

See [flow1-progression-matrix.md](./flow1-progression-matrix.md) for stage progression contracts.
