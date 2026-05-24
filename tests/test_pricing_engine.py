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
    "TIER_1_LIMIT": 1.0,
    "TIER_1_RATE": 0,
    "TIER_2_LIMIT": 1.5,
    "TIER_2_RATE": 150,
    "TIER_3_LIMIT": 3.0,
    "TIER_3_RATE": 350,
    "TIER_4_LIMIT": 3.5,
    "TIER_4_RATE": 500,
    "TIER_5_LIMIT": 4.0,
    "TIER_5_RATE": 550,
    "TIER_6_LIMIT": 4.5,
    "TIER_6_RATE": 700,
    "TIER_7_LIMIT": 5.0,
    "TIER_7_RATE": 750,
    "FINAL_RATE": 950,
}


class TestCalculateDistanceCost:
    def test_minimum_fare_at_0_5km(self):
        assert calculate_distance_cost(0.5, BASE_CONFIG) == 3500

    def test_minimum_fare_at_1_0km(self):
        assert calculate_distance_cost(1.0, BASE_CONFIG) == 3500

    def test_tier_1_to_3km(self):
        # 2.5 km = 3500 + 0.5*150 + 1.0*350 = 3925 -> 3900
        assert calculate_distance_cost(2.5, BASE_CONFIG) == 3900

    def test_tier_1_exact_3km(self):
        # 3.0 km = 3500 + 0.5*150 + 1.5*350 = 4100
        assert calculate_distance_cost(3.0, BASE_CONFIG) == 4100

    def test_tier_3_to_5km(self):
        # 4.0 km = 3500 + 75 + 525 + 250 + 275 = 4625 -> 4600
        assert calculate_distance_cost(4.0, BASE_CONFIG) == 4600

    def test_tier_3_exact_5km(self):
        # 5.0 km = 3500 + 75 + 525 + 250 + 275 + 350 + 375 = 5350 -> rounds to 5400
        assert calculate_distance_cost(5.0, BASE_CONFIG) == 5400

    def test_tier_5plus(self):
        # 7.0 km = 5350 + 2.0*950 = 7250 -> rounds to 7300
        assert calculate_distance_cost(7.0, BASE_CONFIG) == 7300

    def test_rounding_to_nearest_100(self):
        # 1.15 km = 3500 + 0.15*150 = 3522.5 -> 3500
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
        assert result["route_cost"] == 4400  # 4000 + 75 + 350
        assert result["stop_fee"] == 0  # only 1 distance segment
        assert result["segment_fixed_prices"] == 0
        assert result["tools"] == []
        assert result["rain_surcharge"] == 0
        assert result["payment_surcharge"] == 0
        assert result["total"] == 4400

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
        assert result["stop_fee"] == 0  # EXTRA_STOP_FEE is 0
        assert result["route_cost"] == 4600  # 4000 + 75 + 525
        assert result["total"] == 4600  # 4600 + 0

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
        assert result["wait_fee_rate"] == 2000  # informational
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
        
        assert result["rain_surcharge"] == 500
        assert result["total"] == 4500  # 4000 (base) + 500 (rain)

    @pytest.mark.asyncio
    async def test_acompanante_default_no_multiplier(self, config_rows, tool_rows):
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
        assert result["acompanante_multiplier"] == 1.0
        assert result["total"] == 4000  # 4000 * 1.0 (no change)

    @pytest.mark.asyncio
    async def test_tools_appear_with_zero_surcharge(self, config_rows, tool_rows):
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

        assert len(result["tools"]) == 2
        tool_labels = {t["tool"] for t in result["tools"]}
        assert tool_labels == {"Canasta", "Maletín"}
        for t in result["tools"]:
            assert t["surcharge"] == 0
            assert "color" in t
            assert isinstance(t["color"], str)

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
        assert tool_surcharges == 0  # tools have 0 surcharge by default
        assert result["total"] == 4000  # only BASE_FARE at 1.0 km

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
        
        # route_cost (5100) + stop_fee (0) + segment_fixed (8000) = 13100
        # + nequi (500) + rain (500) = 14100
        # ×1 acompanante (default) = 14100
        assert result["wait_fee_rate"] == 2000
        assert result["acompanante_multiplier"] == 1.0
        assert result["total"] == 14100

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
        assert result["wait_fee_rate"] == 2000  # informational
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
        
        assert result["stop_fee"] == 0  # EXTRA_STOP_FEE is 0
