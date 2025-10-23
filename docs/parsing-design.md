# Output Parsing Design

This document captures the decisions and implementation details for TextFSM-based parsing in Tom.

## Executive Summary (decisions made)
- Parsing runs on the **controller** (post-processing), not on workers.
- Workers return raw output only; controller performs parsing on demand.
- Parsing is **explicit**: `parse=true` and optional `template` parameter; explicit template takes precedence.
- Auto-discovery using `ntc-templates` index (platform + command) is supported as an opt-in fallback when no template is provided.
- `ntc-templates` cannot be removed from worker (Netmiko dependency), but worker-side parsing is not used.
- Jobs record minimal metadata (device_type, commands, etc.) so parsing can be performed later when retrieving job results.
- `parse=true` has no effect when `wait=false`; controller logs a warning. Users should either use `wait=true` or request parsing later via `GET /api/job/{job_id}?parse=true`.

## Current State
- Controller exposes parsing APIs and a TextFSM parser module.
- Controller ships with ntc-templates and can additionally accept custom templates via mounted volume `/app/templates/textfsm/`.
- Parser implementation provides two modes:
  - Explicit template: user supplies `template` (highest priority)
  - Auto-discovery: controller uses `device_type` + `command` with ntc-templates index

## Template Locations & Resolution
- Controller filesystem:
  - `/app/templates/textfsm/custom/` (custom templates, override)
  - ntc-templates package (bundled templates)
- Resolution order: `custom` → `ntc-templates` → error

## API Behavior
- Request-time parameters (both GET and POST send-command endpoints):
  - `parse` (bool): request parsing
  - `template` (string): explicit TextFSM template filename
  - `include_raw` (bool): include raw output alongside parsed (default: parsed only)
  - `parser` (string): currently only `textfsm` supported

- Synchronous requests (`wait=true`): controller waits for worker result and, if `parse=true`, returns parsed output (or parsed+raw if `include_raw=true`).
- Asynchronous requests (`wait=false`): `parse=true` is ignored with a logged warning; to parse later, call `GET /api/job/{job_id}?parse=true` which will use job metadata for auto-discovery if no template provided.

- Job metadata now includes minimal args passed to worker (host, port, device_type, commands, credential id) so retrieval-time parsing can access `device_type` and `command`.

## Parsing Function API (controller)
- `parse_output(raw_output, device_type=None, command=None, template=None, include_raw=False, parser_type='textfsm') -> dict`
  - Reusable function callable from any endpoint (synchronous endpoints or job-retrieval).
  - Returns `{'parsed': [...], 'raw': '...'} ` or `{'error': '...', 'raw': '...'}` on failure.

## Tests to Add (automated)
1. Input interface tests (HTTP → job)
   - Verify that GET/POST send-command endpoints enqueue jobs with correct `json` payload (host, device_type, commands, credential info).
   - Use the `JobResponse.metadata` field to assert the job args are stored correctly.

2. Output interface tests (parsing)
   - Provide a packaged test TextFSM template (in `tests/templates/textfsm/`) and a sample raw output fixture.
   - Test explicit template parsing: call `parse_output()` directly and assert parsed structure.
   - Test auto-discovery parsing: simulate job metadata with `device_type` and `command`, call `parse_output()` and assert parsed structure.
   - Test error behavior: missing template → error with raw included if requested.

Suggested test files:
- `tests/fixtures/text_outputs/show_ip_int_brief.txt` (sample raw output)
- `tests/templates/textfsm/test_show_ip_int_brief.textfsm` (simple template that maps to the fixture)
- `tests/test_parsing.py` with unit tests for `parse_output()` and API-level tests using FastAPI test client to validate endpoints.

## Developer Notes & Gotchas
- `ntc-templates` index supports regex-based discovery; discovery is deterministic and transparent (not a black box) but the user can always override by providing `template`.
- `parse=true` on async submission does not perform parsing; relies on retrieval-time parsing using job metadata or embedding parse config into job (we opted for retrieval-time parsing to keep jobs minimal and allow re-parsing with different templates).
- Keep parser library dependencies on controller only (`textfsm`, `ntc-templates`, later `ttp` if added).
- For production deployments on Fargate consider an external object store for templates if templates are updated often; current approach uses mounted volume or baking templates into controller image.

## Next Implementation Steps (short)
- Add unit tests and API tests described above; include a small, deterministic test template in `tests/templates/textfsm/`.
- Document template packaging and how to add custom templates to the controller image or mount them via compose.
- Consider adding a template upload API (Phase 2) and per-device parsing defaults (Phase 3).

---

Document author: automated assistant (changes implemented in codebase). Please run the test suite and add the small test template so CI will validate parsing behavior on subsequent runs.
