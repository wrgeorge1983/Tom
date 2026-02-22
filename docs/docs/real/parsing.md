# Parsing Command Output

Tom can parse raw command output into structured data using TextFSM or TTP templates.

## Specifying a Template

To parse command output, specify a template explicitly:

```bash
curl -X POST "http://localhost:8000/api/device/router1/send_command" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "show version",
    "wait": true,
    "parse": true,
    "template": "cisco_ios_show_version.textfsm"
  }'
```

This returns structured JSON instead of raw text.

## Choosing a Parser

Tom supports two parsing engines:

- **TextFSM** (default) - Regex-based, includes 900+ templates from [ntc-templates](https://github.com/networktocode/ntc-templates)
- **TTP** - Template Text Parser, more readable template syntax. Includes 19 templates from [ttp-templates](https://github.com/dmulyalin/ttp_templates) plus support for custom templates with auto-discovery.

Specify with the `parser` field:

```json
{
  "command": "show version",
  "wait": true,
  "parse": true,
  "parser": "ttp",
  "template": "my_template.ttp"
}
```

## Built-in Template Libraries

Tom includes two template libraries:

- **TextFSM**: [ntc-templates](https://github.com/networktocode/ntc-templates) - over 900 templates covering common commands across Cisco, Arista, Juniper, and many other platforms
- **TTP**: [ttp-templates](https://github.com/dmulyalin/ttp_templates) - 19 templates for Cisco IOS/XR, Arista, Huawei, and Juniper

### Listing Available Templates

```bash
curl "http://localhost:8000/api/templates/textfsm" \
  -H "X-API-Key: your-api-key"
```

### Automatic Template Matching

If you specify `parse=true` but don't specify a template, Tom will attempt to find one automatically based on:

1. **Platform** (from your inventory's `adapter_driver`)
2. **Command** being executed

For example, `show ip interface brief` on a `cisco_ios` device automatically matches `cisco_ios_show_ip_interface_brief.textfsm`:

```bash
curl -X POST "http://localhost:8000/api/device/router1/send_command" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "show ip interface brief",
    "wait": true,
    "parse": true
  }'
```

If no matching template is found, parsing fails with an error.

Both TextFSM (via ntc-templates) and TTP (via ttp-templates) support automatic template discovery based on platform and command.

## Template Source Selection

By default, when looking for a template Tom checks custom templates first, then falls back to the built-in library (ntc-templates for TextFSM, ttp-templates for TTP). You can override this with the `template_source` parameter to force loading from a specific source.

Valid values depend on the parser:

- **TextFSM**: `"custom"` or `"ntc"`
- **TTP**: `"custom"` or `"ttp_templates"`

This is useful when you have a custom template with the same name as a built-in one and need to explicitly select which one to use:

```json
{
  "command": "show version",
  "wait": true,
  "parse": true,
  "template": "cisco_ios_show_version.textfsm",
  "template_source": "ntc"
}
```

`template_source` works with both explicit template names and auto-discovery. When used with auto-discovery (no `template` specified), it restricts which index is searched:

```json
{
  "command": "show version",
  "wait": true,
  "parse": true,
  "template_source": "custom"
}
```

This would only search the custom template index, skipping ntc-templates entirely. If no match is found in the specified source, parsing fails rather than falling back.

The `template_source` parameter is available on all parsing-related endpoints and request models, including `send_command`, `send_commands` (both per-command and as a default), raw endpoints, job result retrieval, and the `/parse/test` endpoint.

### Response Metadata

When parsing succeeds, the response includes `_metadata` indicating which source the template came from:

```json
{
  "parsed": [...],
  "_metadata": {
    "template_source": "ntc",
    "template_name": "cisco_ios_show_version.textfsm"
  }
}
```

## Using Custom Templates

To add your own templates:

1. Create a directory with your template files
2. Mount it into the controller container at `/app/templates/textfsm/` (for TextFSM) or `/app/templates/ttp/` (for TTP)

In your docker-compose:

```yaml
services:
  controller:
    volumes:
      - ./my-templates:/app/templates/textfsm
```

Custom templates take precedence over built-in templates with the same name.

### Template Index Files

For auto-discovery to work with custom templates, you need an `index` file in your template directory. The index maps platform/command combinations to template files:

```
Template, Hostname, Platform, Command
custom_show_version.textfsm, .*, cisco_ios, show version
datacenter_bgp.textfsm, dc-.*, cisco_ios, show ip bgp.*
```

Each column:

- **Template**: Filename of the template in the same directory
- **Hostname**: Regex to match device hostname (use `.*` for all devices)
- **Platform**: Device platform (must match exactly, e.g., `cisco_ios`)
- **Command**: Regex to match the command

When you create templates via the API with `platform` and `command` fields, the index is updated automatically. When you delete a template via the API, its index entry is also removed.

### Template Naming Convention

For automatic matching to work with custom templates, follow the NTC naming convention:

```
{platform}_{command_with_underscores}.textfsm
```

Example: `cisco_ios_show_ip_route.textfsm`

You'll never guess how you should name your TTP templates!

### Creating Templates via the API

You can create custom templates through the API instead of mounting files:

```bash
curl -X POST "http://localhost:8000/api/templates/textfsm" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "custom_show_vlan.textfsm",
    "content": "Value VLAN_ID (\\d+)\nValue NAME (\\S+)\n\nStart\n  ^${VLAN_ID}\\s+${NAME} -> Record\n",
    "platform": "cisco_ios",
    "command": "show vlan"
  }'
```

When `platform` and `command` are provided, the template is automatically registered in the index file for auto-discovery. You can also specify a `hostname` pattern (defaults to `.*`).

## Including Raw Output

To get both parsed and raw output:

```json
{
  "command": "show ip interface brief",
  "wait": true,
  "parse": true,
  "include_raw": true
}
```

Returns:

```json
{
  "parsed": [...],
  "raw": "Interface              IP-Address      OK? Method Status..."
}
```
