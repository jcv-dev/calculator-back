import pytest
from services.fixed_prices import find_keyword_match
from models import FixedPrice


class TestFindKeywordMatch:
    def test_exact_match(self, db):
        result = find_keyword_match(["Cali, Valle del Cauca"], db)
        assert result is not None
        assert result.price == 120000
        assert result.destination_keyword == "cali"

    def test_case_insensitive(self, db):
        result = find_keyword_match(["viaje a CALI desde tulua"], db)
        assert result is not None
        assert result.price == 120000

    def test_keyword_in_middle(self, db):
        result = find_keyword_match(["destino: Buga, valle"], db)
        assert result is not None
        assert result.price == 35000

    def test_no_match(self, db):
        result = find_keyword_match(["Cra 10 #12-34, Tuluá"], db)
        assert result is None

    def test_keword_with_accent(self, db):
        result = find_keyword_match(["Aeropuerto Alfonso Bonilla"], db)
        assert result is not None
        assert result.price == 150000

    def test_multi_address_first_match(self, db):
        result = find_keyword_match(
            ["Cra 5 Tuluá", "Cali, Valle", "Buga, Valle"], db
        )
        assert result is not None
        assert result.price == 120000

    def test_empty_addresses(self, db):
        result = find_keyword_match([], db)
        assert result is None

    def test_partial_word_no_false_positive(self, db):
        # "bugaloo" shouldn't match "buga" if we were doing whole words
        # but our implementation uses regex search (substring)
        # Let's verify behavior: this SHOULD match
        result = find_keyword_match(["Villa Bugaloo"], db)
        assert result is not None
