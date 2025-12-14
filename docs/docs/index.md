# Tom Smykowski Documentation

Welcome to the official documentation for Tom Smykowski, your Network Automation Broker.

## Introduction

- [What is Tom?](real/index.md) - Overview, architecture summary, and design philosophy

## Getting Started

- [Getting Started Sensibly](real/getting-started.md) - Setup with Vault and Redis TLS
- [Getting Started Irresponsibly Fast](real/getting-started-FAST.md) - 5-minute minimal setup

## Core Concepts

- [Architecture](real/architecture.md) - How Tom's components work together
- [Configuration](real/configuration.md) - Config files, environment variables, and validation
- [Parsing](real/parsing.md) - TextFSM and TTP parsing

## Inventory

- [Inventory Overview](real/inventory.md) - How inventory works
- [YAML Inventory](real/inventory-yaml.md) - File-based inventory
- [NetBox](real/inventory-netbox.md) - NetBox integration
- [Nautobot](real/inventory-nautobot.md) - Nautobot integration
- [SolarWinds](real/inventory-solarwinds.md) - SolarWinds NPM integration

## Authentication

- [Authentication Overview](real/authentication.md) - Auth modes and options
- [API Keys](real/auth-api-keys.md) - Simple key-based auth
- [JWT/OAuth](real/auth-jwt.md) - SSO with OAuth providers

## Credentials

- [Vault Credentials](real/vault-credentials.md) - HashiCorp Vault integration (default, recommended)
- [YAML Credentials](real/yaml-credentials.md) - File-based credential store (development only)

## Getting Help

- [Slack](https://networktocode.slack.com/archives/C0A0PER1Y6L) - `#tom_smykowski_nab` channel on Network to Code Slack
- [GitHub Issues](https://github.com/wrgeorge1983/tom/issues) - Bug reports and feature requests