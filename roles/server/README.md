# server role

For machines that provide long-running services to other machines or users.
Service desired state must be versioned, secret references must resolve outside
Git, exposure boundaries must be explicit, and changes require a live health
check after installation.

Ports, credentials, storage paths, capacity limits, and service membership stay
with each host unless multiple machines prove a reusable contract.
