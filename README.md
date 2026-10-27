# AI GPU Fabric — Rail-Optimized Architecture (2x H100)

## 1. Overview
This Containerlab topology defines an 8-rail optimized network fabric connecting two NVIDIA H100 GPU servers (8x GPUs each) through 8 independent leaf switches (`rail1`–`rail8`) and a 2-switch non-blocking spine tier (`spine1`, `spine2`).

* **Topology File:** `ai-gpu-fabric.clab.yml`
* **Management Network:** `clab-ai-fabric` (`172.30.50.0/24`)

---

## 2. Architecture & Design Principles

### Rail-Optimized Design
In a rail-optimized fabric (standard in NVIDIA SuperPOD / DGX H100 architectures):
* GPU $i$ on every server attaches directly to leaf switch `rail[i+1]`.
* Intra-rail communication (e.g. GPU 0 $\leftrightarrow$ GPU 0 across hosts during data-parallel AllReduce) traverses only the leaf tier, achieving single-hop latency without spine congestion.
* Inter-rail communication traverses the non-blocking spine tier (`spine1`, `spine2`).

```
                    ┌────────────────────────┐    ┌────────────────────────┐
                    │      spine1 (SRL)      │    │      spine2 (SRL)      │
                    └───────────┬────────────┘    └───────────┬────────────┘
         ┌──────┬──────┬────────┼───────┬──────┬──────┬───────┼──────┬──────┬──────┬──────┐
         │      │      │        │       │      │      │       │      │      │      │      │
       ┌───┐  ┌───┐  ┌───┐    ┌───┐   ┌───┐  ┌───┐  ┌───┐   ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐
       │ R1│  │ R2│  │ R3│    │ R4│   │ R5│  │ R6│  │ R7│   │ R8│  │ R1│  │ R2│  │ R3│  │ R4│ ...
       └───┘  └───┘  └───┘    └───┘   └───┘  └───┘  └───┘   └───┘  └───┘  └───┘  └───┘  └───┘
         │      │      │        │       │      │      │       │
       gpu0   gpu1   gpu2     gpu3    gpu4   gpu5   gpu6    gpu7
         │      │      │        │       │      │      │       │
  ┌──────┴──────┴──────┴────────┴───────┴──────┴──────┴───────┴──────┐
  │                        gpu-node1 (H100)                          │
  └──────────────────────────────────────────────────────────────────┘
```

---

## 3. Node Inventory

| Tier | Node | Kind | Mgmt IP | Role / Interface Mapping |
|---|---|---|---|---|
| **Spine** | `spine1` | `nokia_srlinux` | `172.30.50.11` | Spine Switch 1 (Downlinks `e1-1`–`e1-8` to Rails 1–8) |
| **Spine** | `spine2` | `nokia_srlinux` | `172.30.50.12` | Spine Switch 2 (Downlinks `e1-1`–`e1-8` to Rails 1–8) |
| **Rail Leaf** | `rail1` | `nokia_srlinux` | `172.30.50.21` | Rail 1 Leaf (Dedicated to GPU 0 on each host) |
| **Rail Leaf** | `rail2` | `nokia_srlinux` | `172.30.50.22` | Rail 2 Leaf (Dedicated to GPU 1 on each host) |
| **Rail Leaf** | `rail3` | `nokia_srlinux` | `172.30.50.23` | Rail 3 Leaf (Dedicated to GPU 2 on each host) |
| **Rail Leaf** | `rail4` | `nokia_srlinux` | `172.30.50.24` | Rail 4 Leaf (Dedicated to GPU 3 on each host) |
| **Rail Leaf** | `rail5` | `nokia_srlinux` | `172.30.50.25` | Rail 5 Leaf (Dedicated to GPU 4 on each host) |
| **Rail Leaf** | `rail6` | `nokia_srlinux` | `172.30.50.26` | Rail 6 Leaf (Dedicated to GPU 5 on each host) |
| **Rail Leaf** | `rail7` | `nokia_srlinux` | `172.30.50.27` | Rail 7 Leaf (Dedicated to GPU 6 on each host) |
| **Rail Leaf** | `rail8` | `nokia_srlinux` | `172.30.50.28` | Rail 8 Leaf (Dedicated to GPU 7 on each host) |
| **Compute** | `gpu-node1` | `linux` | `172.30.50.101` | H100 Server 1 (`gpu0`–`gpu7` on subnets `10.100.1.0/24`–`10.100.8.0/24`) |
| **Compute** | `gpu-node2` | `linux` | `172.30.50.102` | H100 Server 2 (`gpu0`–`gpu7` on subnets `10.100.1.0/24`–`10.100.8.0/24`) |
