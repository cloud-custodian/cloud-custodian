def evaluate_result(action, resources):
    if action == "allow" and resources:
        result = "allow"
    elif action == "allow" and not resources:
        result = "deny"
    elif action == "deny" and resources:
        result = "deny"
    elif action == "deny" and not resources:
        result = "allow"
    elif action == "warn" and resources:
        result = "warn"
    elif action == "warn" and not resources:
        result = "allow"

    return result
