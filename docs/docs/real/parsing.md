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

## 

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

### Template Naming Convention

For automatic matching to work with custom templates, follow the NTC naming convention:

```
{platform}_{command_with_underscores}.textfsm
```

Example: `cisco_ios_show_ip_route.textfsm`

You'll never guess how you should name your TTP templates!

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
