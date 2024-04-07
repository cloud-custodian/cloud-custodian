def get_firewall_port_ranges(firewall_resources):
    for r_index, r in enumerate(firewall_resources):
        action = "allowed" if "allowed" in r else "denied"
        for protocol_index, protocol in enumerate(r[action]):
            if "ports" in protocol:
                port_ranges = []
                for port in protocol["ports"]:
                    if "-" in port:
                        port_split = port.split("-")
                        port_ranges.append({"beginPort": port_split[0], "endPort": port_split[1]})
                    else:
                        port_ranges.append({"beginPort": port, "endPort": port})
                protocol['portRanges'] = port_ranges
                r[action][protocol_index] = protocol
        firewall_resources[r_index] = r
    return firewall_resources
