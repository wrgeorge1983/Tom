# Output Parsing

Tom Controller includes integrated output parsing to transform raw network device command output into structured data.

## Overview

**Parsers Supported:**
- **TextFSM** - Pattern-based parsing with 929 built-in ntc-templates
- **TTP** - Template Text Parser with flexible template support

**Key Features:**
- Auto-discovery based on device platform and command
- Custom template support with index-based registration
- Template source visibility (custom vs built-in)
- Explicit template selection when needed
- **Per-command parsing control** for multi-command requests (v0.7.1+)

## Basic Usage

### Auto-Discovery

Add `parse=true` to any command request. Tom automatically selects the appropriate template:

```bash
curl "http://localhost:8000/api/device/router1/send_command?command=show+ip+interface+brief&parse=true&wait=true"
```

Response:
```json
{
  "parsed": [
    {"interface": "GigabitEthernet0/0", "ip_address": "10.1.1.1", "status": "up", "proto": "up"}
  ],
  "_metadata": {
    "template_source": "ntc-templates",
    "template_name": "cisco_ios_show_ip_interface_brief.textfsm"
  }
}
```

### Explicit Template Selection

Specify a template explicitly:

```bash
curl "http://localhost:8000/api/device/router1/send_command?command=show+version&parse=true&template=my_custom_template.textfsm&wait=true"
```

### Parser Selection

Default is TextFSM. Use TTP by specifying `parser=ttp`:

```bash
curl "http://localhost:8000/api/device/router1/send_command?command=show+interfaces&parse=true&parser=ttp&wait=true"
```

### Per-Command Parsing (Multiple Commands)

When sending multiple commands, you can control parsing individually:

```bash
curl -X POST "http://localhost:8000/api/device/router1/send_commands" \
  -H "Content-Type: application/json" \
  -d '{
    "commands": [
      {
        "command": "show version",
        "parse": true,
        "template": "custom_version.textfsm"
      },
      {
        "command": "show ip bgp summary",
        "parse": true,
        "parser": "ttp"
      },
      {
        "command": "show running-config",
        "parse": false
      }
    ],
    "wait": true
  }'
```

This allows you to:
- Use different parsers for different commands
- Specify templates per command
- Skip parsing for specific commands (e.g., large configs)
- Mix TextFSM and TTP in the same request

## Custom Templates

### Directory Structure

```
/app/templates/
├── textfsm/
│   ├── index                    # Template registry
│   └── my_template.textfsm      # Your templates
└── ttp/
    ├── index                    # Template registry
    └── my_template.ttp          # Your templates
```

### Creating Custom Templates

**1. Create your template file:**

`templates/textfsm/my_bgp_parser.textfsm`:
```textfsm
Value NEIGHBOR (\S+)
Value AS_NUMBER (\d+)
Value STATE (\S+)

Start
  ^${NEIGHBOR}\s+\d+\s+${AS_NUMBER}\s+\S+\s+\S+\s+\S+\s+${STATE} -> Record
```

**2. Register it in the index:**

`templates/textfsm/index`:
```csv
Template, Hostname, Platform, Command
my_bgp_parser.textfsm, .*, cisco_ios, show ip bgp summary
```

**3. Restart controller - your template is now active**

### Index Format

CSV format with 4 columns:

- **Template**: Filename in the same directory
- **Hostname**: Regex to match device hostname (use `.*` for all)
- **Platform**: Device platform from inventory (e.g., `cisco_ios`, `arista_eos`)
- **Command**: Regex to match the command

**Examples:**
```csv
Template, Hostname, Platform, Command
datacenter_bgp.textfsm, dc-.*, cisco_ios, show ip bgp.*
router_version.textfsm, router-[0-9]+, cisco_ios, show version
generic_interfaces.textfsm, .*, arista_eos, show interfaces
```

## Template Selection Order

### TextFSM
1. Explicit template via `?template=` parameter
2. Custom index (`/app/templates/textfsm/index`)
3. ntc-templates built-in index (929 templates)
4. Error if no match

### TTP
1. Explicit template via `?template=` parameter  
2. Inline template via `template_string` (API only)
3. Custom index (`/app/templates/ttp/index`)
4. Error if no match

*Note: TTP has no built-in templates, only custom ones.*

## Response Metadata

All parsed responses include `_metadata` showing template selection:

```json
{
  "parsed": [...],
  "_metadata": {
    "template_source": "custom",
    "template_name": "my_bgp_parser.textfsm"
  }
}
```

**`template_source` values:**
- `"explicit"` - Template specified via `?template=` parameter
- `"custom"` - Template from custom index
- `"ntc-templates"` - Built-in template (TextFSM only)
- `"inline"` - Inline template string (TTP only)

## API Endpoints

### Parse Single Command Output

```
GET /api/device/{device}/send_command
  ?command=show+version
  &parse=true
  &parser=textfsm          # optional, default: textfsm
  &template=my_template    # optional, explicit template
  &wait=true
```

### Parse Multiple Commands with Per-Command Control

```
POST /api/device/{device}/send_commands
```

Request body with per-command parsing configuration:
```json
{
  "commands": [
    {
      "command": "show version",
      "parse": true,
      "parser": "textfsm",
      "template": "custom_version.textfsm"
    },
    {
      "command": "show interfaces",
      "parse": true,
      "parser": "ttp",
      "template": "interfaces.ttp"
    },
    {
      "command": "show running-config",
      "parse": false  // Don't parse, return raw
    }
  ],
  "wait": true
}
```

### Parse Job Results

```
GET /api/job/{job_id}
  ?parse=true
  &parser=textfsm
  &template=my_template    # Note: Same template applied to all commands
```

### List Available Templates

```
GET /api/templates/textfsm
GET /api/templates/ttp
```

Returns:
```json
{
  "custom": ["my_template.textfsm", "another_template.textfsm"],
  "ntc": ["cisco_ios_show_version.textfsm", ...]
}
```

## TextFSM Template Development

TextFSM uses regular expressions to extract structured data. Example:

```textfsm
Value INTERFACE (\S+)
Value IP_ADDRESS (\S+)
Value STATUS (up|down|administratively down)
Value PROTOCOL (up|down)

Start
  ^${INTERFACE}\s+${IP_ADDRESS}\s+\w+\s+\w+\s+${STATUS}\s+${PROTOCOL} -> Record
```

**Resources:**
- [TextFSM on GitHub](https://github.com/google/textfsm)
- [ntc-templates](https://github.com/networktocode/ntc-templates) - 929 examples

## TTP Template Development

TTP uses a simpler template syntax. Example:

```ttp
<group name="interfaces">
{{ interface }} is {{ admin_state }}, line protocol is {{ protocol_state }}
  Hardware is {{ hardware }}
  Internet address is {{ ip_address }}/{{ mask }}
  MTU {{ mtu }} bytes
</group>
```

**Resources:**
- [TTP Documentation](https://ttp.readthedocs.io/)

## Configuration

Template directories are configured in `tom_controller_config.yaml`:

```yaml
textfsm_template_dir: /app/templates/textfsm
ttp_template_dir: /app/templates/ttp
```

Default docker-compose mounts `./templates:/app/templates`.

## Troubleshooting

### Template Not Found

Check:
1. Template file exists in correct directory
2. Filename matches entry in `index` file exactly
3. `index` file has correct CSV format with header
4. Docker volume mount is correct

Note: Changes to templates or indexes take effect immediately.

### Template Not Matching

Check:
1. Platform in index matches device `device_type` from inventory
2. Command regex in index matches your command
3. Check logs for template selection: `docker-compose logs controller`

### Parse Errors

Check:
1. Template patterns match your device output format
2. Include `include_raw=true` to see raw output: `?parse=true&include_raw=true`
3. Test template with sample output first

## Performance

- Template files and indexes are read from disk on each parse request
- Template changes take effect immediately (no restart required)
- Parsing happens on controller (not workers)
- Results are not cached

## Limitations

- Parsing requires `wait=true` for synchronous execution
- Only one template applied per command
- No template chaining or fallback patterns
- Template discovery requires exact platform match
