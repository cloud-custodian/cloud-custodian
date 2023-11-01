def get_firewall_port_ranges(ports):
    port_ranges = []
    for port in ports:
            if "-" in port:
                port_split = port.split("-")
                port_ranges.append({"beginPort": port_split[0], "endPort": port_split[1]})
            else:
                port_ranges.append({"beginPort": port, "endPort": port})
    return port_ranges