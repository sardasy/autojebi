"""Two bounded execution lanes; HWP serialization remains inside its Worker."""

LOCAL_KINDS = frozenset({"verify", "excel", "package"})


def lane_for(kind: str) -> str:
    return "local" if kind in LOCAL_KINDS else "external"


def validate_lane(lane: str) -> str:
    if lane not in {"all", "local", "external"}:
        raise ValueError("invalid execution lane")
    return lane
