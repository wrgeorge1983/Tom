<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./docs/images/Tom-BlkBlueTrans_1000x1000.png">
  <img alt="Text changing depending on mode. Light: 'So light!' Dark: 'So dark!'" src="./docs/images/Tom-BlkWhiteTrans_1000x1000.png" width="256">
</picture>

# Tom Smykowski

Tom Smykowski is your Network Automation Broker: He takes the network state FROM 
your equipment and gives it TO your developers. He deals with your damn equipment,
so the developers don't have to!

It's like a jump-host for your applications, with all the network automation fiddly
bits taken care of.

## What would you say you do here?
There are lots of things a good network automation project will need, and most of 
them have no reason to be re-invented every time. 

Also, convenience and consistency aside, the service talking directly to users via
a web interface, or chat, etc. has NO business talking directly to your network 
equipment or handling credentials etc. Big teams of great engineers build insecure 
web and chat interfaces ALL THE TIME, and the last thing we want to do is show up 
on some pentest as The Weakest Link.  

Network Automation has a huge toolbox, and integrating with all of it (especially 
doing so well, and securely) is a huge challenge. 

- **Transport/Drivers** - Netmiko, scrapli, etc.
- **Parsing engines and templates** - TextFSM, ttp, genie, etc.
- **Rendering templates** - Jinja2, ttp, etc.
- **Inventory** - TBD - something about talking to a SOT to get device inventory, 
  map it to transport drivers, etc
- **Security** - TBD - something about managing credentials, maybe also RBAC

All of these are solveable, but there's rarely a reason to solve them differently for
each project.  Also, they can be cumbersome and fragile with unpleasant dependence on
system details (looking at you, Templating Libraries!)


## Goals

- **Reusable primitives** - Provide common functionality (templating, parsing, SOT & Inventory integration, queueing, API glue) that can be consumed by multiple automation workflows or tools.
- **Simple deployments** - A single `docker compose` setup for running all services together with dependencies (e.g., Redis).
- **Support runtime changes** - You can update your service config as time goes on
- **Support immutable state** - You can bake your own images so you're guaranteed to have an always redeployable artifact without a bunch of setup or external dependencies.


## Inspiration

- [Netpalm](https://github.com/tbotnz/netpalm/) - Netpalm effectively invented the idea of a Network Automation Broker, and is the direct inspiration for Tom Smykowski.


## License
Code is MIT - see [LICENSE](./LICENSE)  
Art is licensed for limited usage - see [ART-LICENSE](./ART_LICENSE.txt)
