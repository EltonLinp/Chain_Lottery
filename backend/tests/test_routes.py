import importlib
import json
import os
import unittest
from unittest import mock

import werkzeug

import backend.config as config_module

# Compatibility shim for Flask expecting werkzeug.__version__
if not hasattr(werkzeug, "__version__"):  # pragma: no cover
    werkzeug.__version__ = "3.0.0"


class TicketRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["RPC_URL"] = "http://localhost:8545"
        os.environ["LOTTERY_CONTRACT_ADDRESS"] = "0x" + "0" * 40
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        os.environ["ADMIN_API_KEY"] = "test-admin"
        config_module.load_settings.cache_clear()

        import backend.services.tickets as tickets_service_module
        import backend.services.draws as draws_service_module
        import backend.routes.tickets as tickets_route_module
        import backend.routes.admin as admin_route_module
        import backend.db as db_module
        import backend.models as models_module
        import backend.app as app_module

        importlib.reload(config_module)
        importlib.reload(db_module)
        importlib.reload(tickets_service_module)
        importlib.reload(draws_service_module)
        importlib.reload(tickets_route_module)
        importlib.reload(admin_route_module)
        importlib.reload(models_module)
        app_module = importlib.reload(app_module)

        self.app = app_module.create_app()
        self.client = self.app.test_client()
        periods_resp = self.client.get("/admin/api/periods", headers=self._headers())
        self.assertEqual(periods_resp.status_code, 200)
        periods_initial = periods_resp.get_json()
        self.assertGreaterEqual(len(periods_initial), 1)

    def tearDown(self) -> None:
        config_module.load_settings.cache_clear()

    def _headers(self):
        return {"X-Admin-Token": "test-admin"}

    @mock.patch("backend.routes.tickets.get_blockchain_client")
    def test_purchase_ticket(self, mock_client_factory):
        mock_client = mock.AsyncMock()
        mock_client.get_current_period.return_value = 1
        mock_client_factory.return_value = mock_client

        response = self.client.post(
            "/tickets",
            data=json.dumps({"numbers": [1, 2, 3, 4, 5, 6]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["period_id"], 1)
        self.assertEqual(payload["status"], "pending")
        self.assertIn("ticket_id", payload)

        history_resp = self.client.get("/tickets")
        self.assertEqual(history_resp.status_code, 200)
        history = history_resp.get_json()
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["period_id"], 1)
        self.assertEqual(history[0]["status"], "pending")

        resp_periods = self.client.get("/admin/api/periods", headers=self._headers())
        self.assertEqual(resp_periods.status_code, 200)
        periods = resp_periods.get_json()
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0]["ticket_count"], 1)

    @mock.patch("backend.routes.admin.get_blockchain_client")
    @mock.patch("backend.routes.tickets.get_blockchain_client")
    def test_claim_ticket(self, mock_ticket_client_factory, mock_admin_client_factory):
        mock_ticket_client = mock.AsyncMock()
        mock_ticket_client.get_current_period.return_value = 1
        mock_ticket_client.claim_prize.return_value = "0xabc"
        mock_ticket_client_factory.return_value = mock_ticket_client

        mock_admin_client = mock.AsyncMock()
        mock_admin_client._account = object()  # simulate configured signer
        mock_admin_client.get_current_period.side_effect = [1, 2]
        mock_admin_client.get_period.return_value = {
            "status": "Selling",
            "result_set": False,
            "winning_numbers": [],
            "ticket_count": 0,
            "total_sales": 0,
            "paid_out": 0,
        }
        mock_admin_client.close_current_period.return_value = "0xclose"
        mock_admin_client.submit_result.return_value = "0xsubmit"
        mock_admin_client.settle_period.return_value = "0xsettle"
        mock_admin_client.open_next_period.return_value = "0xopen"
        mock_admin_client_factory.return_value = mock_admin_client

        create_resp = self.client.post(
            "/tickets",
            data=json.dumps({"numbers": [1, 2, 3, 4, 5, 6]}),
            content_type="application/json",
        )
        ticket_id = create_resp.get_json()["ticket_id"]

        draw_resp = self.client.post(
            "/admin/api/draws",
            headers=self._headers(),
            data=json.dumps({"period_id": 1, "winning_numbers": [1, 2, 3, 4, 30, 31]}),
            content_type="application/json",
        )
        self.assertEqual(draw_resp.status_code, 200)
        draw_payload = draw_resp.get_json()
        self.assertEqual(draw_payload["period_id"], 1)
        self.assertEqual(draw_payload["current_period"], 2)
        self.assertIn("transactions", draw_payload)
        self.assertIn("submit_result", draw_payload["transactions"])

        # After draw submission, the mocked blockchain estimate is no longer used
        # but keep return value to avoid unexpected awaits.
        mock_ticket_client.estimate_matches.return_value = 4

        response = self.client.post(f"/tickets/{ticket_id}/claim")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["tx_hash"], "0xabc")
        self.assertEqual(payload["payout"], str(4 * 100))

        history_resp = self.client.get("/tickets")
        self.assertEqual(history_resp.status_code, 200)
        history = history_resp.get_json()
        self.assertTrue(any(t["ticket_id"] == ticket_id and t["status"] == "claimed" for t in history))


if __name__ == "__main__":
    unittest.main()
