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

---

## 4. Fabric Routing & RoCEv2 Lossless Profile

### BGP Underlay Routing
* **Spine AS:** `65000` (Spine 1 router-id `10.255.0.11`, Spine 2 router-id `10.255.0.12`)
* **Leaf AS:** `65021`–`65028` (`rail1` through `rail8`)
* **ECMP Multipathing:** Enabled (`multipath ebgp maximum-paths 64`) on all switches.
* **Inter-Rail Routing:** Dual-homed uplinks from each rail leaf to `spine1` and `spine2` provide 2 equal-cost paths to all other rails.
* **Intra-Rail Switching:** L2 MAC-VRF bridge domains on each leaf switch provide direct single-hop switching between server GPUs on the same rail with line-rate forwarding.

### RoCEv2 Lossless Network Configuration
* **Jumbo MTU:** Port MTU `9216`, IP MTU `9000`, L2 MTU `9200` on switch interfaces and host GPU interfaces (`gpu0`–`gpu7`).
* **PFC (Priority Flow Control):** Priority 3 lossless queue mapped to forwarding-class `fc3` via 802.1p (`dot1p-policy rocev2-pfc`) and DSCP 24/26 (`dscp-policy rocev2-dscp`).
* **ECN / DCQCN:** Explicit Congestion Notification globally enabled on all SR Linux nodes (`qos explicit-congestion-notification`) with WRED ECN slope configured in queue-management-profile `rocev2-ecn` (min-threshold 20%, max-threshold 80%).
* **Host ECN:** `net.ipv4.tcp_ecn = 1` enabled on compute containers.

---

## 5. Automation & Lifecycle Commands

```bash
# 1. Deploy the topology
sudo clab deploy -t ai-gpu-fabric.clab.yml

# 2. Automatically configure BGP, RoCEv2, and compute interfaces
python3 configure_fabric.py

# 3. Verify BGP sessions on Spine switches
docker exec clab-ai-gpu-fabric-spine1 sr_cli "show network-instance default protocols bgp neighbor"
docker exec clab-ai-gpu-fabric-spine2 sr_cli "show network-instance default protocols bgp neighbor"

# 4. Verify end-to-end Jumbo Frame connectivity across all 8 rails
docker exec clab-ai-gpu-fabric-gpu-node1 bash -c '
for i in {1..8}; do
  ping -c 2 -W 2 -M do -s 8972 -I gpu$((i-1)) 10.100.$i.2 && echo "Rail $i OK"
done
'

# 5. Teardown
sudo clab destroy -t ai-gpu-fabric.clab.yml --cleanup
```
