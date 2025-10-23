# Custom Templates

This directory contains custom parsing templates for Tom Controller.

## Directory Structure

- `textfsm/` - Custom TextFSM templates
- `ttp/` - Custom TTP templates

## Usage

### TextFSM Templates

#### Option 1: Explicit Template Selection

Place `.textfsm` files in the `textfsm/` directory and reference them explicitly:

Example: `textfsm/my_custom_parser.textfsm`

To use in an API call:
```
GET /api/device/{device}/send_command?command=show+version&parse=true&template=my_custom_parser.textfsm
```

#### Option 2: Auto-Discovery with Custom Index

Register templates for automatic selection by creating `textfsm/index`:

**Format:** CSV with columns: `Template, Hostname, Platform, Command`

**Example `textfsm/index`:**
```csv
Template, Hostname, Platform, Command
custom_show_version.textfsm, .*, cisco_ios, show version
datacenter_bgp.textfsm, dc-.*, cisco_ios, show ip bgp.*
special_interfaces.textfsm, router-[0-9]+, cisco_ios, show ip int.*
```

**Fields:**
- `Template`: Filename in the textfsm/ directory
- `Hostname`: Regex to match device hostname (use `.*` for all devices)
- `Platform`: Device platform from inventory (e.g., `cisco_ios`, `arista_eos`)
- `Command`: Regex to match the command

**Lookup Order:**
1. Custom templates in `textfsm/index` (checked first)
2. ntc-templates built-in index (929 templates - automatic fallback)

**API call with auto-discovery:**
```
GET /api/device/router1/send_command?command=show+version&parse=true
```
Tom will automatically select the best template based on device platform and command.

### TTP Templates

#### Option 1: Explicit Template Selection

Place `.ttp` files in the `ttp/` directory and reference them explicitly:

Example: `ttp/my_custom_parser.ttp`

To use in an API call:
```
GET /api/device/{device}/send_command?command=show+version&parse=true&parser=ttp&template=my_custom_parser.ttp
```

#### Option 2: Auto-Discovery with Custom Index

Register templates for automatic selection by creating `ttp/index`:

**Format:** CSV with columns: `Template, Hostname, Platform, Command`

**Example `ttp/index`:**
```csv
Template, Hostname, Platform, Command
custom_show_interfaces.ttp, .*, cisco_ios, show interfaces
datacenter_bgp.ttp, dc-.*, cisco_ios, show ip bgp.*
special_version.ttp, router-[0-9]+, cisco_ios, show version
```

**Fields:**
- `Template`: Filename in the ttp/ directory
- `Hostname`: Regex to match device hostname (use `.*` for all devices)
- `Platform`: Device platform from inventory (e.g., `cisco_ios`, `arista_eos`)
- `Command`: Regex to match the command

**Note:** Unlike TextFSM, TTP has no built-in templates, so the custom index is the only way to enable auto-discovery for TTP parsing.

**API call with auto-discovery:**
```
GET /api/device/router1/send_command?command=show+interfaces&parse=true&parser=ttp
```
Tom will automatically select the best template based on device platform and command.

## Listing Available Templates

To see all available templates:
```
GET /api/templates/textfsm
```

This will return custom templates and built-in ntc-templates.
