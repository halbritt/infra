# Infrastructure

This context records the managed resources and desired state used to operate
Halbritt's computing environment.

## Language

**Infrastructure**:
The complete managed set of hosts, devices, services, providers, and reusable
configuration represented by this repository.
_Avoid_: Fleet, proximal

**Host**:
A physical machine, virtual machine, or operating-system instance with its own
identity and host-level desired state.
_Avoid_: Box, server, node when the distinction is not relevant

**Device**:
A managed appliance whose primary lifecycle and configuration are exposed
through a device control plane rather than a general-purpose host interface.
_Avoid_: Host

**Resource name**:
A stable, repository-wide identity that distinguishes one managed resource from
possible siblings without depending on its current address or network hostname.
_Avoid_: Hostname, display name

**Observed hostname**:
The network hostname currently reported by a resource. It can differ from the
resource name while a rename is pending or when the resource has no hostname.
_Avoid_: Resource name

**Service**:
An operational system whose desired state is managed independently of any one
host, even when a host currently runs it.
_Avoid_: Subsystem, app

**Provider**:
An external infrastructure control plane and the resource declarations managed
through it.
_Avoid_: Cloud, vendor

**Fleet**:
A group of like resources operated together, such as the host fleet or GPU
fleet. It is not the name of this repository or its complete domain.
_Avoid_: Infrastructure

**Role**:
A reusable host responsibility or machine-type contract that declares shared
inputs without owning host-specific state.
_Avoid_: Host profile, template

**Shared configuration**:
Configuration whose bytes and meaning are proven reusable by more than one
consumer.
_Avoid_: Default, common
