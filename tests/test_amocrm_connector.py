from time import time
from unittest.mock import Mock

import unittest

from amocrm_connector import AmoCRMConnector, AmoCRMError, AmoCRMToken


class AmoCRMConnectorTests(unittest.TestCase):
    def _build_connector(self, session: Mock) -> AmoCRMConnector:
        token = AmoCRMToken(
            access_token="old_token",
            refresh_token="refresh_token",
            expires_at=time() + 3600,
        )
        return AmoCRMConnector(
            base_domain="example",
            client_id="client",
            client_secret="secret",
            redirect_uri="https://example.com/callback",
            token=token,
            session=session,
        )

    def test_get_leads_success(self) -> None:
        session = Mock()
        api_response = Mock(status_code=200)
        api_response.json.return_value = {
            "_embedded": {"leads": [{"id": 1, "name": "Lead #1"}]}
        }
        session.request.return_value = api_response

        connector = self._build_connector(session)
        leads = connector.get_leads(limit=10, page=2)

        self.assertEqual(leads, [{"id": 1, "name": "Lead #1"}])
        session.request.assert_called_once()

    def test_refresh_token_when_expired(self) -> None:
        session = Mock()

        refresh_response = Mock(status_code=200)
        refresh_response.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_in": 1800,
        }
        session.post.return_value = refresh_response

        api_response = Mock(status_code=200)
        api_response.json.return_value = {"_embedded": {"leads": []}}
        session.request.return_value = api_response

        connector = self._build_connector(session)
        connector.token.expires_at = time() - 1

        connector.get_leads()

        self.assertEqual(connector.token.access_token, "new_access")
        self.assertEqual(connector.token.refresh_token, "new_refresh")
        session.post.assert_called_once()
        session.request.assert_called_once()

    def test_raise_error_on_api_failure(self) -> None:
        session = Mock()
        api_response = Mock(status_code=401, text="Unauthorized")
        session.request.return_value = api_response

        connector = self._build_connector(session)

        with self.assertRaises(AmoCRMError):
            connector.get_leads()


if __name__ == "__main__":
    unittest.main()
