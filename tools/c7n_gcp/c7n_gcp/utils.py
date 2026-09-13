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


def parse_protobuf_duration_to_seconds(duration):
    """Convert a protobuf Duration string (for example ``2592000s``) to int seconds."""
    expected_format = "Expected format <seconds>s (e.g. 2592000s)."

    if duration is None:
        return None

    if not isinstance(duration, str):
        raise ValueError(
            f"Expected protobuf duration as string. {expected_format} "
            f"got {type(duration).__name__}"
        )

    duration_value = duration.strip()
    if not duration_value.endswith('s'):
        raise ValueError(
            f"Invalid protobuf duration format: {duration}. {expected_format}"
        )

    try:
        return int(duration_value[:-1])
    except (TypeError, ValueError):
        raise ValueError(
            f"Invalid protobuf duration format: {duration}. {expected_format}"
        )
