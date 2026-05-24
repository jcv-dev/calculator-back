import pytest
import pytest_asyncio
from models import FixedPrice
from services.fixed_prices import find_keyword_match, find_proximity_match

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def kw_only_db(db):
    db.add(FixedPrice(
        service_type=None,
        destination_keyword="cali",
        price=120000,
        description="Tarifa fija Tuluá → Cali (keyword-only)",
        lat=None,
        lng=None,
        radius_km=None,
    ))
    db.add(FixedPrice(
        service_type=None,
        destination_keyword="buga",
        price=35000,
        description="Tarifa fija Tuluá → Buga (keyword-only)",
        lat=None,
        lng=None,
        radius_km=None,
    ))
    db.add(FixedPrice(
        service_type=None,
        destination_keyword="aeropuerto",
        price=150000,
        description="Tarifa fija Tuluá → Aeropuerto (keyword-only)",
        lat=None,
        lng=None,
        radius_km=None,
    ))
    await db.commit()
    return db


class TestFindKeywordMatch:
    async def test_exact_match(self, kw_only_db):
        result = await find_keyword_match(["Cali, Valle del Cauca"], kw_only_db)
        assert result is not None
        assert result.price == 120000
        assert result.destination_keyword == "cali"

    async def test_case_insensitive(self, kw_only_db):
        result = await find_keyword_match(["viaje a CALI desde tulua"], kw_only_db)
        assert result is not None
        assert result.price == 120000

    async def test_keyword_in_middle(self, kw_only_db):
        result = await find_keyword_match(["destino: Buga, valle"], kw_only_db)
        assert result is not None
        assert result.price == 35000

    async def test_no_match(self, kw_only_db):
        result = await find_keyword_match(["Cra 10 #12-34, Tuluá"], kw_only_db)
        assert result is None

    async def test_keword_with_accent(self, kw_only_db):
        result = await find_keyword_match(["Aeropuerto Alfonso Bonilla"], kw_only_db)
        assert result is not None
        assert result.price == 150000

    async def test_multi_address_first_match(self, kw_only_db):
        result = await find_keyword_match(
            ["Cra 5 Tuluá", "Cali, Valle", "Buga, Valle"], kw_only_db
        )
        assert result is not None
        assert result.price == 120000

    async def test_empty_addresses(self, kw_only_db):
        result = await find_keyword_match([], kw_only_db)
        assert result is None

    async def test_partial_word_no_false_positive(self, kw_only_db):
        result = await find_keyword_match(["Villa Bugaloo"], kw_only_db)
        assert result is None

    async def test_keyword_excludes_rows_with_coords(self, db):
        # The default seed "cali" row has lat/lng — should NOT match via keyword
        result = await find_keyword_match(["Cali, Valle del Cauca"], db)
        assert result is None


class TestFindProximityMatch:
    @pytest_asyncio.fixture
    async def proximity_only_db(self, db):
        db.add(FixedPrice(
            service_type=None,
            destination_keyword=None,
            price=50000,
            description="Solo proximidad",
            lat=3.45,
            lng=-76.53,
            radius_km=20,
        ))
        await db.commit()
        return db

    async def test_proximity_only_match(self, proximity_only_db):
        result = await find_proximity_match(3.45, -76.53, ["Cra 10 Tuluá"], proximity_only_db)
        assert result is not None
        assert result.price == 50000

    async def test_proximity_out_of_radius(self, db):
        # Tuluá centro is ~80km from Cali, well outside 20km radius
        result = await find_proximity_match(4.0847, -76.1954, ["Cra 10 Tuluá"], db)
        assert result is None

    async def test_and_logic_keyword_coords_both_match(self, db):
        # "Aeropuerto Alfonso Bonilla" matches keyword AND coords
        result = await find_proximity_match(3.5432, -76.3816, ["Aeropuerto Alfonso Bonilla"], db)
        assert result is not None
        assert result.destination_keyword == "aeropuerto"

    async def test_and_logic_keyword_mismatch_skips_row(self, db):
        # Coords are within aeropuerto radius, but keyword "aeropuerto" not in address
        result = await find_proximity_match(3.5432, -76.3816, ["Cerca del aerodromo"], db)
        assert result is None

    async def test_and_logic_proximity_mismatch_skips_row(self, db):
        # Keyword "aeropuerto" matches, but coords are far away
        result = await find_proximity_match(4.0847, -76.1954, ["Aeropuerto Alfonso Bonilla"], db)
        assert result is None
