VERSION = "v2"


def notify(number, enabled):
    """Simulate delivery to a confirmation endpoint after the commit."""
    if not enabled:
        raise ConnectionError("Confirmation endpoint unreachable")
    return f"ACK-{number:06d}"
