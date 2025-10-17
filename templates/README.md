# Custom Templates

This directory contains custom parsing templates for Tom Controller.

## Directory Structure

- `textfsm/` - Custom TextFSM templates
- `ttp/` - Custom TTP templates

## Usage

### TextFSM Templates

Place `.textfsm` files in the `textfsm/` directory. These templates will override ntc-templates with the same name.

Example: `textfsm/my_custom_parser.textfsm`

To use in an API call:
```
GET /api/device/{device}/send_command?command=show+version&parse=true&parser=textfsm&template=my_custom_parser.textfsm
```

### TTP Templates

Place `.ttp` files in the `ttp/` directory.

Example: `ttp/my_custom_parser.ttp`

To use in an API call:
```
GET /api/device/{device}/send_command?command=show+version&parse=true&parser=ttp&template=my_custom_parser.ttp
```

## Listing Available Templates

To see all available templates:
```
GET /api/templates/textfsm
```

This will return custom templates and built-in ntc-templates.
