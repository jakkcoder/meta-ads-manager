import pytest
from unittest.mock import MagicMock, patch

from app.meta.client import MetaAPIError, MetaClient
from app.config import Settings


@pytest.fixture
def settings():
    return Settings(meta_access_token="test_token", ad_account_id="1579547858935909")


def test_ad_account_path(settings):
    assert settings.ad_account_path == "act_1579547858935909"


def test_meta_api_error():
    err = MetaAPIError("rate limited", code=17, subcode=244)
    assert err.code == 17
    assert str(err) == "rate limited"


@patch("app.meta.client.httpx.Client")
def test_get_ad_account(mock_client_cls, settings):
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "act_123", "name": "Test Account"}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.request.return_value = mock_response
    mock_client_cls.return_value = mock_client

    client = MetaClient(settings)
    result = client.get_ad_account()
    assert result["name"] == "Test Account"


@patch("app.meta.client.httpx.Client")
def test_raises_on_api_error(mock_client_cls, settings):
    mock_response = MagicMock()
    mock_response.json.return_value = {"error": {"message": "Invalid token", "code": 190}}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.request.return_value = mock_response
    mock_client_cls.return_value = mock_client

    client = MetaClient(settings)
    with pytest.raises(MetaAPIError, match="Invalid token"):
        client.get_ad_account()
