import pytest

from empirical_platform.identifiers import CampaignId, ReviewId


def test_identifier_accepts_valid_value() -> None:
    assert str(CampaignId("CAMP-0001")) == "CAMP-0001"


def test_identifier_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        ReviewId("CAMP-0001")
