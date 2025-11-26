# Tom Smykowski Documentation

## Overview

Tom Smykowski is a Network Automation Broker that takes network state FROM your equipment and gives it TO your developers. He deals with your network equipment, so the developers don't have to.

Think of Tom as a jump-host for your applications, with all the network automation complexities handled for you.

## The Problem

Network automation projects consistently require the same foundational components, yet these are often re-implemented for each project. More critically, services that interact directly with users through web interfaces or chat applications should not communicate directly with network equipment or manage credentials. Security vulnerabilities in user-facing services are common, even among experienced engineering teams, and creating a direct path to network infrastructure creates unnecessary risk.

The network automation ecosystem offers a substantial toolbox—transport drivers, parsing engines, template renderers, inventory systems, and credential management—but integrating these components well and securely represents a significant engineering challenge that shouldn't be repeated for every project.

## What Tom Provides

Tom serves as a centralized broker that handles:

- **Transport and Drivers**: Integration with Netmiko, scrapli, and other connectivity frameworks
- **Parsing**: Support for TextFSM, TTP, and other parsing engines with 900+ built-in templates
- **Inventory Management**: Plugin-based system supporting YAML, SolarWinds SWIS, Nautobot, and NetBox
- **Security**: HashiCorp Vault integration for credentials, JWT/OAuth2 authentication for users
- **Queue Management**: Asynchronous job processing with per-device concurrency control
- **Caching**: Redis-backed response caching to reduce load on device management planes

## Architecture

Tom uses a controller-worker architecture with Redis as the message broker:

```mermaid
sequenceDiagram
    actor C as Client 
    participant T as Tom Controller
    participant R as Redis Queue
    participant W as Tom Worker
    participant D as Network Device
        
    C ->> T: /send_command
        note over C,T: device=R1<br/>command="sh ip int bri"
    T ->> T: Validate auth & lookup inventory
    T ->> R: Queue job
    R -->> W: Dispatch job
    W ->> W: Lookup credential
    W ->> D: Execute command
    activate D
        D -->> W: Raw output
    deactivate D
    W ->> W: Parse if requested
    W ->> R: Store result
    R -->> T: Job complete
    T -->> C: Return result
```

### Components

**Controller**: FastAPI-based REST API that handles authentication, inventory lookups, and job queueing. The controller never directly connects to network devices.

**Worker**: Executes network commands using Netmiko or scrapli adapters. Workers retrieve credentials from Vault, manage per-device concurrency, and handle response parsing.

**Redis**: Provides job queueing via SAQ (Simple Async Queue) and response caching.

## Project Status

**Beta** - Tom is feature-complete for core functionality. All major features are implemented and the project is stable for production use, though the API may evolve based on real-world feedback. Where multiple variations of a feature are planned, typically one implementation currently exists.

## Design Philosophy

- **Reusable primitives**: Common functionality (templating, parsing, inventory integration, queueing) consumable by multiple automation workflows
- **Simple deployments**: Single docker-compose setup for all services and dependencies
- **Runtime flexibility**: Service configuration can be updated without rebuilding images
- **Immutable deployment option**: Ability to bake custom images for guaranteed redeployable artifacts

## Next Steps

- [Getting Started Fast](getting-started-FAST.md) - 5-minute minimal setup
- [Getting Started Sensibly](getting-started.md) - More complete setup with Vault
- [Architecture](architecture.md) - How Tom's components work together
- [Parsing](parsing.md) - Using TextFSM and TTP parsers
- [API Documentation](http://localhost:8000/docs) - Swagger UI (when Tom is running)
