#!/usr/bin/env python3
"""
AI GPU Fabric Configuration Script
Automates:
- eBGP underlay between spines (AS 65000) and rail leaves (AS 65021..65028)
- ECMP multipathing across spines (maximum-paths 64)
- RoCEv2 lossless network parameters (MTU 9216, PFC Priority 3, ECN/DCQCN)
- IRB + MAC-VRF bridging on rail leaves for intra-rail L2 switching & inter-rail L3 routing
- Compute node MTU 9216 and IP configuration on gpu0..gpu7
"""

import subprocess
import sys
import time

def run_sr_cli(container, commands):
    script = "\n".join(commands) + "\n"
    print(f"[*] Applying configuration to {container}...")
    res = subprocess.run(
        ["docker", "exec", "-i", container, "sr_cli"],
        input=script,
        text=True,
        capture_output=True
    )
    if res.returncode != 0:
        print(f"[-] Error on {container}: {res.stderr or res.stdout}")
        return False
    print(f"[+] Successfully configured {container}")
    return True

def run_host_cmd(container, cmd):
    res = subprocess.run(
        ["docker", "exec", container] + cmd,
        text=True,
        capture_output=True
    )
    if res.returncode != 0:
        print(f"[-] Host cmd error on {container} ({cmd}): {res.stderr}")
    return res.returncode == 0

def configure_spine(spine_id):
    container = f"clab-ai-gpu-fabric-spine{spine_id}"
    router_id = f"10.255.0.1{spine_id}"
    asn = 65000
    
    cmds = [
        "enter candidate",
        # Loopback
        "set / interface system0 admin-state enable subinterface 0 admin-state enable ipv4 admin-state enable address " + router_id + "/32",
        
        # QoS RoCEv2 lossless profile & ECN
        "set / qos queues queue unicast-3 queue-index 3",
        "set / qos queues queue multicast-3 queue-index 3",
        "set / qos forwarding-classes forwarding-class fc3 output unicast-queue unicast-3 multicast-queue multicast-3",
        "set / qos explicit-congestion-notification",
        "set / qos classifiers dot1p-policy rocev2-pfc dot1p 3 forwarding-class fc3",
        "set / qos classifiers dscp-policy rocev2-dscp dscp 24 forwarding-class fc3",
        "set / qos classifiers dscp-policy rocev2-dscp dscp 26 forwarding-class fc3",
        "set / qos buffer-management queue-management-profile rocev2-ecn wred wred-slope all drop-probability all enable-ecn true min-threshold 20 max-threshold 80 slope-enabled true max-drop-probability-percent 100",
        
        # Routing policy to export connected routes
        "set / routing-policy policy export-connected default-action policy-result accept",
        
        # Default network-instance & BGP
        "set / network-instance default type default",
        "set / network-instance default interface system0.0",
        "set / network-instance default protocols bgp autonomous-system " + str(asn),
        "set / network-instance default protocols bgp router-id " + router_id,
        "set / network-instance default protocols bgp ebgp-default-policy import-reject-all false",
        "set / network-instance default protocols bgp ebgp-default-policy export-reject-all false",
        "set / network-instance default protocols bgp export-policy [ export-connected ]",
        "set / network-instance default protocols bgp afi-safi ipv4-unicast admin-state enable",
        "set / network-instance default protocols bgp afi-safi ipv4-unicast multipath ebgp maximum-paths 64",
        "set / network-instance default protocols bgp group ebgp-rails admin-state enable",
        "set / network-instance default protocols bgp group ebgp-rails afi-safi ipv4-unicast admin-state enable",
    ]
    
    # 8 Downlinks to rail leaves: e1-1 through e1-8
    # Spine 1 uses 10.0.10.x..10.0.17.x; Spine 2 uses 10.0.20.x..10.0.27.x
    base_prefix = f"10.0.{spine_id}0."
    for r in range(1, 9):
        p2p_sub = f"10.0.{spine_id}{r-1}"
        spine_ip = f"{p2p_sub}.1/30"
        rail_ip = f"{p2p_sub}.2"
        rail_asn = 65020 + r
        port = f"ethernet-1/{r}"
        
        cmds.extend([
            f"set / interface {port} admin-state enable mtu 9216",
            f"set / interface {port} ethernet flow-control receive true",
            f"set / interface {port} subinterface 0 admin-state enable ip-mtu 9000 ipv4 admin-state enable address {spine_ip}",
            f"set / network-instance default interface {port}.0",
            f"set / network-instance default protocols bgp neighbor {rail_ip} peer-group ebgp-rails peer-as {rail_asn} admin-state enable",
        ])
        
    cmds.append("commit now")
    return run_sr_cli(container, cmds)

def configure_rail(rail_id):
    container = f"clab-ai-gpu-fabric-rail{rail_id}"
    router_id = f"10.255.0.2{rail_id}"
    rail_asn = 65020 + rail_id
    gpu_subnet_gw = f"10.100.{rail_id}.254/24"
    
    cmds = [
        "enter candidate",
        # Loopback
        f"set / interface system0 admin-state enable subinterface 0 admin-state enable ipv4 admin-state enable address {router_id}/32",
        
        # QoS RoCEv2 profile & ECN
        "set / qos queues queue unicast-3 queue-index 3",
        "set / qos queues queue multicast-3 queue-index 3",
        "set / qos forwarding-classes forwarding-class fc3 output unicast-queue unicast-3 multicast-queue multicast-3",
        "set / qos explicit-congestion-notification",
        "set / qos classifiers dot1p-policy rocev2-pfc dot1p 3 forwarding-class fc3",
        "set / qos classifiers dscp-policy rocev2-dscp dscp 24 forwarding-class fc3",
        "set / qos classifiers dscp-policy rocev2-dscp dscp 26 forwarding-class fc3",
        "set / qos buffer-management queue-management-profile rocev2-ecn wred wred-slope all drop-probability all enable-ecn true min-threshold 20 max-threshold 80 slope-enabled true max-drop-probability-percent 100",
        
        # Downlinks to Compute Nodes (e1-1 -> gpu-node1, e1-2 -> gpu-node2)
        "set / interface ethernet-1/1 admin-state enable mtu 9216",
        "set / interface ethernet-1/1 ethernet flow-control receive true",
        "set / interface ethernet-1/1 subinterface 0 admin-state enable type bridged l2-mtu 9200",
        "set / interface ethernet-1/2 admin-state enable mtu 9216",
        "set / interface ethernet-1/2 ethernet flow-control receive true",
        "set / interface ethernet-1/2 subinterface 0 admin-state enable type bridged l2-mtu 9200",
        
        # IRB for gateway and MAC-VRF bridge domain
        f"set / interface irb0 admin-state enable subinterface 0 admin-state enable ip-mtu 9000 ipv4 admin-state enable address {gpu_subnet_gw}",
        f"set / network-instance rail{rail_id}-bd type mac-vrf admin-state enable",
        f"set / network-instance rail{rail_id}-bd interface ethernet-1/1.0",
        f"set / network-instance rail{rail_id}-bd interface ethernet-1/2.0",
        f"set / network-instance rail{rail_id}-bd interface irb0.0",
        
        # Uplinks to Spines
        # e1-3 to spine1:e1-{rail_id} (10.0.1{rail_id-1}.2/30)
        # e1-4 to spine2:e1-{rail_id} (10.0.2{rail_id-1}.2/30)
        f"set / interface ethernet-1/3 admin-state enable mtu 9216",
        f"set / interface ethernet-1/3 ethernet flow-control receive true",
        f"set / interface ethernet-1/3 subinterface 0 admin-state enable ip-mtu 9000 ipv4 admin-state enable address 10.0.1{rail_id-1}.2/30",
        f"set / interface ethernet-1/4 admin-state enable mtu 9216",
        f"set / interface ethernet-1/4 ethernet flow-control receive true",
        f"set / interface ethernet-1/4 subinterface 0 admin-state enable ip-mtu 9000 ipv4 admin-state enable address 10.0.2{rail_id-1}.2/30",
        
        # Routing Policy to export connected (irb0.0, loopback, P2P)
        "set / routing-policy policy export-connected default-action policy-result accept",
        
        # Default network-instance & eBGP
        "set / network-instance default type default",
        "set / network-instance default interface system0.0",
        "set / network-instance default interface irb0.0",
        "set / network-instance default interface ethernet-1/3.0",
        "set / network-instance default interface ethernet-1/4.0",
        f"set / network-instance default protocols bgp autonomous-system {rail_asn}",
        f"set / network-instance default protocols bgp router-id {router_id}",
        "set / network-instance default protocols bgp ebgp-default-policy import-reject-all false",
        "set / network-instance default protocols bgp ebgp-default-policy export-reject-all false",
        "set / network-instance default protocols bgp export-policy [ export-connected ]",
        "set / network-instance default protocols bgp afi-safi ipv4-unicast admin-state enable",
        "set / network-instance default protocols bgp afi-safi ipv4-unicast multipath ebgp maximum-paths 64",
        "set / network-instance default protocols bgp group ebgp-spines admin-state enable",
        "set / network-instance default protocols bgp group ebgp-spines afi-safi ipv4-unicast admin-state enable",
        f"set / network-instance default protocols bgp neighbor 10.0.1{rail_id-1}.1 peer-group ebgp-spines peer-as 65000 admin-state enable",
        f"set / network-instance default protocols bgp neighbor 10.0.2{rail_id-1}.1 peer-group ebgp-spines peer-as 65000 admin-state enable",
        
        "commit now"
    ]
    return run_sr_cli(container, cmds)

def configure_compute_nodes():
    print("[*] Configuring GPU compute nodes (MTU 9216, IP addressing, ECN)...")
    nodes = {
        "clab-ai-gpu-fabric-gpu-node1": 1,
        "clab-ai-gpu-fabric-gpu-node2": 2
    }
    for cname, node_num in nodes.items():
        print(f"[*] Setting up {cname}...")
        # ECN sysctl
        run_host_cmd(cname, ["sysctl", "-w", "net.ipv4.tcp_ecn=1"])
        
        for k in range(8):
            iface = f"gpu{k}"
            rail_id = k + 1
            ip = f"10.100.{rail_id}.{node_num}/24"
            # Flush existing addresses if any
            run_host_cmd(cname, ["ip", "addr", "flush", "dev", iface])
            # Set MTU 9216 and bring up
            run_host_cmd(cname, ["ip", "link", "set", "dev", iface, "mtu", "9216", "up"])
            # Assign IP
            run_host_cmd(cname, ["ip", "addr", "add", ip, "dev", iface])
            
        print(f"[+] Configured all 8 GPU interfaces on {cname}")

def main():
    print("=" * 60)
    print("AI GPU FABRIC CONFIGURATION - NOKIA SR LINUX & COMPUTE NODES")
    print("=" * 60)
    
    # 1. Configure Spines
    for s in (1, 2):
        if not configure_spine(s):
            sys.exit(1)
            
    # 2. Configure Rail Leaves
    for r in range(1, 9):
        if not configure_rail(r):
            sys.exit(1)
            
    # 3. Configure Compute Nodes
    configure_compute_nodes()
    
    print("\n[+] All network configurations applied successfully!")

if __name__ == "__main__":
    main()
