# Tom Smykowski

Tom Smykowski is your Network Automation Broker: He takes the network state FROM 
your equipment and gives it TO your developers. He deals with your damn equipment,
so the developers don't have to!

It's like a jump-host for your applications.

## Why - (what don't you people understand!?)
There are lots of things a good network automation project will need, and most of 
them have no reason to be re-invented every time. 

Also, convenience and consistency aside, the service talking directly to users via
a web interface, or chat, etc. has NO business talking directly to your network 
equipment or handling credentials etc. 

All of these are solveable, but there's rarely a reason to solve it differently for
each project.  Also, they can be cumbersome and fragile with unpleasant dependence
system details (looking at you TextFSM!) 

- **Transport/Drivers** - Netmiko, scrapli, etc.
- **Parsing engines and templates** - TextFSM, ttp, genie, etc.
- **Rendering templates** - Jinja2, ttp, etc.
- **Inventory** - TBD - something about talking to a SOT to get device inventory, 
  map it to transport drivers, etc
- **Security** - TBD - something about managing credentials, maybe also RBAC


## Goals

- **Reusable primitives** - Provide common functionality (templating, parsing, queue handling, API glue) that can be consumed by multiple automation workflows or tools.
- **Simple deployments** - A single `docker compose` setup for running all services together with dependencies (e.g., Redis).
- **Support runtime changes** - You can update your service config as time goes on
- **Support immutable state** - You can bake your own images so you're guaranteed to have an always redeployable artifact without a bunch of setup

