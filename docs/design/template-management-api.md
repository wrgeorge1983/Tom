# Template Management API - Design Doc

**Status:** Implemented  
**Date:** 2026-01-27

## Overview

Extended the template inspection/management capabilities to allow users to list, view, create, and delete parsing templates.

## Implemented Endpoints

### Existing

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/templates/textfsm` | GET | List all TextFSM templates |
| `/api/templates/match` | GET | Find matching template for device_type/command |
| `/api/parse/test` | POST | Test parsing with a template |

### New

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/templates/ttp` | GET | List all TTP templates |
| `/api/templates/{parser}/{name}` | GET | View template contents |
| `/api/templates/{parser}` | POST | Create/upload a custom template |
| `/api/templates/{parser}/{name}` | DELETE | Delete a custom template |

## Design Decisions

### 1. Naming Conventions

**Decision:** No enforcement of naming conventions for custom templates.

**Rationale:** Users may want to create templates that are only used with explicit `template=` parameters, not auto-discovery. Forcing `{device_type}_{command}.{ext}` naming would be unnecessarily restrictive.

### 2. Template Persistence

**Decision:** Templates are written directly to the filesystem. If the directory is not writable, the request fails with a clear error.

**Rationale:** Deployment configuration (volume mounts, etc.) is the user's responsibility. Tom should not make assumptions about the deployment environment. Users are expected to "prime" Tom with templates as part of their deployment process.

### 3. Template Validation

**Decision:** 
- TextFSM templates are compiled using `textfsm.TextFSM()` to validate syntax
- TTP templates are instantiated with `ttp()` to catch initialization errors
- Validation errors are returned as warnings, but the template is still created

**Rationale:** TextFSM has robust compile-time validation. TTP is more lenient and doesn't raise on most syntax issues. By creating the template regardless of validation warnings, users can still use templates that may be valid despite warnings.

### 4. Deletion Restrictions

**Decision:** Only custom templates can be deleted. Attempting to delete an ntc-template returns HTTP 400.

**Rationale:** ntc-templates are bundled with the application and should not be modified. Deleting them would be confusing since they'd reappear after a rebuild.

### 5. TTP Template Listing

**Decision:** The TTP listing endpoint returns `{"custom": [...], "ttp_templates": [...]}` including templates from the [ttp-templates](https://github.com/dmulyalin/ttp_templates) package.

## API Details

### GET /api/templates/ttp

List all TTP templates.

**Response:**
```json
{
  "custom": ["my_template.ttp", "another.ttp"]
}
```

### GET /api/templates/{parser}/{name}

Get template contents.

**Parameters:**
- `parser`: "textfsm" or "ttp"
- `name`: Template filename (extension optional)

**Response:**
```json
{
  "name": "cisco_ios_show_version.textfsm",
  "parser": "textfsm",
  "source": "ntc",
  "content": "Value VERSION (\\S+)\\n..."
}
```

### POST /api/templates/{parser}

Create a custom template.

**Request:**
```json
{
  "name": "my_template.textfsm",
  "content": "Value HOSTNAME (\\S+)\\n\\nStart\\n  ^${HOSTNAME}",
  "overwrite": false
}
```

**Response:**
```json
{
  "name": "my_template.textfsm",
  "parser": "textfsm",
  "created": true,
  "validation_warnings": null
}
```

If validation fails:
```json
{
  "name": "my_template.textfsm",
  "parser": "textfsm",
  "created": true,
  "validation_warnings": ["TextFSM syntax error: Unknown syntax at line 3"]
}
```

### DELETE /api/templates/{parser}/{name}

Delete a custom template.

**Response:**
```json
{
  "name": "my_template.textfsm",
  "deleted": true
}
```

**Errors:**
- 404: Template not found
- 400: Cannot delete ntc-template

## Security Considerations

- Path traversal prevention: Template names cannot contain `/`, `\`, or `..`
- Only custom templates can be deleted
- Template content is not executed, only stored

## Not Implemented

The following was considered but not implemented:

### View Template Fields/Variables

**Endpoint:** `GET /api/templates/{parser}/{name}/fields`

**Reason for deferral:** Adds complexity for marginal benefit. Users can read the template content directly. Could be added later if there's demand.
