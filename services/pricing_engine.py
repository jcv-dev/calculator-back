from models import FareConfig, Tool


def config_to_dict(config_rows: list[FareConfig]) -> dict[str, float]:
    return {row.key: row.value for row in config_rows}


def _collect_tiers(config: dict[str, float]) -> list[tuple[float, float]]:
    tiers = []
    i = 1
    while True:
        limit = config.get(f"TIER_{i}_LIMIT")
        rate = config.get(f"TIER_{i}_RATE")
        if limit is None or rate is None:
            break
        tiers.append((limit, rate))
        i += 1
    tiers.sort(key=lambda t: t[0])
    return tiers


def calculate_distance_cost(total_km: float, config: dict[str, float]) -> int:
    base_fare = int(config.get("BASE_FARE", 4000))
    tiers = _collect_tiers(config)
    final_rate = config.get("FINAL_RATE", 500)

    if not tiers:
        return base_fare

    cost = float(base_fare)
    prev = 0.0

    for limit_km, rate in tiers:
        if total_km <= prev:
            break
        if total_km <= limit_km:
            cost += (total_km - prev) * rate
            break
        cost += max(0, limit_km - prev) * rate
        prev = limit_km
    else:
        if total_km > prev:
            cost += (total_km - prev) * final_rate

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

    # Wait fee — not applied automatically, just reported for informational warnings
    wait_fee_rate = int(cfg.get("WAIT_FEE", 3000))

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
        "wait_fee_rate": wait_fee_rate,
        "acompanante": acompanante,
        "acompanante_multiplier": float(cfg.get("ACOMPANANTE_MULTIPLIER", 1.0)),
        "segments": segment_details,
        "total": 0,
    }

    if acompanante and breakdown["acompanante_multiplier"] != 1.0:
        total *= breakdown["acompanante_multiplier"]

    breakdown["total"] = round(total)
    return breakdown
