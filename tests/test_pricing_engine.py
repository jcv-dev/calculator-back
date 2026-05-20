import pytest
from services.pricing_engine import (
    calculate_distance_cost,
    calculate_full_price,
    count_distance_segments,
    count_fixed_price_segments,
    config_to_dict,
)

BASE_CONFIG = {
    "BASE_FARE": 3500,
    "EXTRA_STOP_FEE": 1500,
    "TOOL_CANASTA": 1000,
    "TOOL_MALETIN": 500,
    "METODO_NEQUI_SURCHARGE": 500,
    "RAIN_SURCHARGE": 1000,
}


class TestCalculateDistanceCost:
    def test_minimum_fare_at_0_5km(self):
        assert calculate_distance_cost(0.5, BASE_CONFIG) == 3500

    def test_minimum_fare_at_1_0km(self):
        assert calculate_distance_cost(1.0, BASE_CONFIG) == 3500

    def test_tier_1_to_3km(self):
        # 2.5 km = 3500 + (1.5 * 200) = 3800
        assert calculate_distance_cost(2.5, BASE_CONFIG) == 3800

    def test_tier_1_exact_3km(self):
        # 3.0 km = 3500 + (2.0 * 200) = 3900
        assert calculate_distance_cost(3.0, BASE_CONFIG) == 3900

    def test_tier_3_to_5km(self):
        # 4.0 km = 3500 + (2.0 * 200) + (1.0 * 300) = 4200
        assert calculate_distance_cost(4.0, BASE_CONFIG) == 4200

    def test_tier_3_exact_5km(self):
        # 5.0 km = 3500 + 400 + 600 = 4500
        assert calculate_distance_cost(5.0, BASE_CONFIG) == 4500

    def test_tier_5plus(self):
        # 7.0 km = 3500 + 400 + 600 + (2.0 * 500) = 5500
        assert calculate_distance_cost(7.0, BASE_CONFIG) == 5500

    def test_rounding_to_nearest_100(self):
        # 1.15 km = 3500 + (0.15 * 200) = 3530 -> rounded to 3500
        assert calculate_distance_cost(1.15, BASE_CONFIG) == 3500


class TestCountDistanceSegments:
    def test_all_distance(self):
        segs = [
            {"service_type": "domicilios", "has_coords": True},
            {"service_type": "mensajeria", "has_coords": True},
        ]
        assert count_distance_segments(segs) == 2

    def test_mixed_with_fixed(self):
        segs = [
            {"service_type": "domicilios", "has_coords": True},
            {"service_type": "purchases", "has_coords": False},
            {"service_type": "mensajeria", "has_coords": True},
        ]
        assert count_distance_segments(segs) == 2

    def test_all_fixed(self):
        segs = [
            {"service_type": "purchases", "has_coords": False},
            {"service_type": "bancarios", "has_coords": False},
        ]
        assert count_distance_segments(segs) == 0

    def test_empty(self):
        assert count_distance_segments([]) == 0


class TestCountFixedPriceSegments:
    def test_mixed(self):
        segs = [
            {"fixed_price": 0},
            {"fixed_price": 8000},
            {"fixed_price": 5000},
        ]
        assert count_fixed_price_segments(segs) == 13000

    def test_none_fixed(self):
        segs = [
            {"fixed_price": 0},
            {"fixed_price": 0},
        ]
        assert count_fixed_price_segments(segs) == 0

    def test_empty(self):
        assert count_fixed_price_segments([]) == 0


class TestCalculateFullPrice:
    @pytest.mark.asyncio
    async def test_basic_delivery(self, config_rows, tool_rows):
        segs = [
            {"service_type": "domicilios", "has_coords": True, "fixed_price": 0},
        ]
        result = await calculate_full_price(
            segments=segs,
            total_km=2.5,
            tools=[],
            payment_method="efectivo",
            acompanante=False,
            is_raining=False,
            config_rows=config_rows,
            tool_rows=tool_rows,
        )
        assert result["route_cost"] == 4300  # 4000 + (1.5 * 200)
        assert result["stop_fee"] == 0  # only 1 distance segment
        assert result["segment_fixed_prices"] == 0
        assert result["tools"] == []
        assert result["rain_surcharge"] == 0
        assert result["payment_surcharge"] == 0
        assert result["total"] == 4300

    @pytest.mark.asyncio
    async def test_two_distance_segments_stop_fee(self, config_rows, tool_rows):
        segs = [
            {"service_type": "domicilios", "has_coords": True, "fixed_price": 0},
            {"service_type": "mensajeria", "has_coords": True, "fixed_price": 0},
        ]
        result = await calculate_full_price(
            segments=segs,
            total_km=3.0,
            tools=[],
            payment_method="efectivo",
            acompanante=False,
            is_raining=False,
            config_rows=config_rows,
            tool_rows=tool_rows,
        )
        assert result["stop_fee"] == 1500  # 1 extra stop
        assert result["route_cost"] == 4400  # 4000 + (2.0 * 200)
        assert result["total"] == 5900  # 4400 + 1500

    @pytest.mark.asyncio
    async def test_mixed_distance_and_fixed_segments(self, config_rows, tool_rows):
        segs = [
            {"service_type": "domicilios", "has_coords": True, "fixed_price": 0},
            {"service_type": "purchases", "has_coords": False, "fixed_price": 8000},
        ]
        result = await calculate_full_price(
            segments=segs,
            total_km=1.0,
            tools=[],
            payment_method="efectivo",
            acompanante=False,
            is_raining=False,
            config_rows=config_rows,
            tool_rows=tool_rows,
        )
        assert result["route_cost"] == 4000  # BASE_FARE (1.0 km)
        assert result["stop_fee"] == 0  # only 1 distance segment
        assert result["segment_fixed_prices"] == 8000
        assert result["total"] == 12000  # 4000 + 8000

    @pytest.mark.asyncio
    async def test_nequi_surcharge(self, config_rows, tool_rows):
        segs = [
            {"service_type": "domicilios", "has_coords": True, "fixed_price": 0},
        ]
        result = await calculate_full_price(
            segments=segs,
            total_km=1.0,
            tools=[],
            payment_method="nequi",
            acompanante=False,
            is_raining=False,
            config_rows=config_rows,
            tool_rows=tool_rows,
        )
        
        assert result["payment_surcharge"] == 500
        assert result["total"] == 4500  # 4000 (base) + 500 (nequi)

    @pytest.mark.asyncio
    async def test_rain_surcharge(self, config_rows, tool_rows):
        segs = [
            {"service_type": "domicilios", "has_coords": True, "fixed_price": 0},
        ]
        result = await calculate_full_price(
            segments=segs,
            total_km=1.0,
            tools=[],
            payment_method="efectivo",
            acompanante=False,
            is_raining=True,
            config_rows=config_rows,
            tool_rows=tool_rows,
        )
        
        assert result["rain_surcharge"] == 1000
        assert result["total"] == 5000  # 4000 (base) + 1000 (rain)

    @pytest.mark.asyncio
    async def test_acompanante_doubles(self, config_rows, tool_rows):
        segs = [
            {"service_type": "domicilios", "has_coords": True, "fixed_price": 0},
        ]
        result = await calculate_full_price(
            segments=segs,
            total_km=1.0,
            tools=[],
            payment_method="efectivo",
            acompanante=True,
            is_raining=False,
            config_rows=config_rows,
            tool_rows=tool_rows,
        )
        
        assert result["acompanante"] is True
        assert result["total"] == 8000  # 4000 * 2

    @pytest.mark.asyncio
    async def test_tools_surcharge(self, config_rows, tool_rows):
        segs = [
            {"service_type": "domicilios", "has_coords": True, "fixed_price": 0},
        ]
        result = await calculate_full_price(
            segments=segs,
            total_km=1.0,
            tools=["canasta", "maletin"],
            payment_method="efectivo",
            acompanante=False,
            is_raining=False,
            config_rows=config_rows,
            tool_rows=tool_rows,
            )
        
        tool_surcharges = sum(t["surcharge"] for t in result["tools"])
        assert tool_surcharges == 1500
        assert result["total"] == 5500  # 4000 + 1000 + 500

    @pytest.mark.asyncio
    async def test_all_modifiers_stacked(self, config_rows, tool_rows):
        segs = [
            {"service_type": "domicilios", "has_coords": True, "fixed_price": 0},
            {"service_type": "mensajeria", "has_coords": True, "fixed_price": 0},
            {"service_type": "purchases", "has_coords": False, "fixed_price": 8000},
        ]
        result = await calculate_full_price(
            segments=segs,
            total_km=4.0,
            tools=["canasta"],
            payment_method="nequi",
            acompanante=True,
            is_raining=True,
            config_rows=config_rows,
            tool_rows=tool_rows,
            )
        
        # route_cost (4700) + stop_fee (1500) + segment_fixed (8000) = 14200
        # + canasta (1000) + nequi (500) + rain (1000) = 16700
        # ×2 acompanante = 33400
        assert result["total"] == 33400

    @pytest.mark.asyncio
    async def test_zero_distance_fixed_only(self, config_rows, tool_rows):
        segs = [
            {"service_type": "purchases", "has_coords": False, "fixed_price": 8000},
        ]
        result = await calculate_full_price(
            segments=segs,
            total_km=0.0,
            tools=[],
            payment_method="efectivo",
            acompanante=False,
            is_raining=False,
            config_rows=config_rows,
            tool_rows=tool_rows,
        )
        assert result["route_cost"] == 0  # no distance segments → no base fare
        assert result["segment_fixed_prices"] == 8000
        assert result["stop_fee"] == 0
        assert result["total"] == 8000

    @pytest.mark.asyncio
    async def test_three_distance_segments(self, config_rows, tool_rows):
        segs = [
            {"service_type": "domicilios", "has_coords": True, "fixed_price": 0},
            {"service_type": "mensajeria", "has_coords": True, "fixed_price": 0},
            {"service_type": "tramites", "has_coords": True, "fixed_price": 0},
        ]
        result = await calculate_full_price(
            segments=segs,
            total_km=5.0,
            tools=[],
            payment_method="efectivo",
            acompanante=False,
            is_raining=False,
            config_rows=config_rows,
            tool_rows=tool_rows,
        )
        
        assert result["stop_fee"] == 3000  # 2 extra stops × 1500
