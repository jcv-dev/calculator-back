from models import FareConfig, Tool


def config_to_dict(config_rows: list[FareConfig]) -> dict[str, float]:
    return {row.key: row.value for row in config_rows}


def calculate_distance_cost(total_km: float, config: dict[str, float]) -> int:
    base_fare = int(config.get("BASE_FARE", 4000))

    if total_km <= 1.0:
        return base_fare

    cost = float(base_fare)

    if total_km <= 3.0:
        cost += (total_km - 1.0) * 200
    elif total_km <= 5.0:
        cost += 2.0 * 200 + (total_km - 3.0) * 300
    else:
        cost += 2.0 * 200 + 2.0 * 300 + (total_km - 5.0) * 500

    return int(cost / 100 + 0.5) * 100


PAYMENT_SURCHARGE_METHODS = {"nequi"}


def count_distance_segments(segments: list[dict]) -> int:
    return sum(
        1 for s in segments if s.get("has_coords")
    )


def count_fixed_price_segments(segments: list[dict]) -> float:
    return sum(
        s.get("fixed_price", 0) or 0 for s in segments
    )


async def calculate_full_price(
    segments: list[dict],
    total_km: float,
    tools: list[str],
    payment_method: str,
    acompanante: bool,
    is_raining: bool,
    config_rows: list[FareConfig],
    tool_rows: list[Tool] | None = None,
    base_price: int | None = None,
) -> dict:
    cfg = config_to_dict(config_rows)

    distance_seg_count = count_distance_segments(segments)

    if base_price is not None:
        route_cost = base_price
        stop_fee = 0
        segment_fixed_total = 0
    else:
        if distance_seg_count == 0:
            route_cost = 0
        else:
            route_cost = calculate_distance_cost(total_km, cfg)

        extra_stops = max(0, distance_seg_count - 1)
        stop_fee = extra_stops * int(cfg.get("EXTRA_STOP_FEE", 1500))

        segment_fixed_total = count_fixed_price_segments(segments)

    total = float(route_cost) + stop_fee + segment_fixed_total

    # Tools — resolved from Tool table rows (dynamic)
    tool_map = {}
    if tool_rows:
        tool_map = {t.key: t for t in tool_rows if t.active}

    active_tools = []
    for tool_key in tools:
        tool = tool_map.get(tool_key)
        if tool and tool.surcharge > 0:
            surcharge = int(tool.surcharge)
            total += surcharge
            active_tools.append({"tool": tool.label, "surcharge": surcharge})

    # Payment method surcharge
    payment_surcharge = 0
    if payment_method.lower() in PAYMENT_SURCHARGE_METHODS:
        surcharge = int(cfg.get("METODO_NEQUI_SURCHARGE", 500))
        payment_surcharge = surcharge
        total += surcharge

    # Rain surcharge
    rain_surcharge = 0
    if is_raining:
        surcharge = int(cfg.get("RAIN_SURCHARGE", 1000))
        rain_surcharge = surcharge
        total += surcharge

    # Per-segment breakdown
    distance_segments = [s for s in segments if s.get("has_coords")]
    non_distance_segments = [s for s in segments if not s.get("has_coords")]
    total_distance_segments = len(distance_segments)

    segment_details = []

    if total_distance_segments > 0 and total_km > 0:
        km_per_segment = total_km / total_distance_segments
        for i, seg in enumerate(distance_segments):
            seg_cost = calculate_distance_cost(km_per_segment, cfg)
            segment_details.append({
                "index": segments.index(seg),
                "label": seg.get("label", seg.get("service_type", "")),
                "cost": seg_cost,
                "type": "distance",
            })
        # Adjust last segment to make sum match (due to rounding in tier formula)
        if len(segment_details) > 1 and total_distance_segments > 0:
            distance_sum = sum(s["cost"] for s in segment_details)
            diff = route_cost - distance_sum
            if diff != 0:
                segment_details[-1]["cost"] += diff
    elif total_distance_segments == 1:
        seg = distance_segments[0]
        segment_details.append({
            "index": segments.index(seg),
            "label": seg.get("label", seg.get("service_type", "")),
            "cost": route_cost,
            "type": "distance",
        })

    for seg in non_distance_segments:
        segment_details.append({
            "index": segments.index(seg),
            "label": seg.get("label", seg.get("service_type", "")),
            "cost": int(seg.get("fixed_price", 0)),
            "type": "fixed",
        })

    breakdown = {
        "total_km": total_km,
        "route_cost": route_cost,
        "stop_fee": stop_fee,
        "segment_fixed_prices": segment_fixed_total,
        "tools": active_tools,
        "payment_surcharge": payment_surcharge,
        "rain_surcharge": rain_surcharge,
        "acompanante": acompanante,
        "segments": segment_details,
        "total": 0,
    }

    if acompanante:
        total *= 2.0

    breakdown["total"] = round(total)
    return breakdown
