"""Focused correctness checks for monetary accounting and pagination boundaries."""
import unittest
from unittest.mock import patch, Mock
from pathlib import Path
import tempfile

from client import APIError, Client, save_json, read_json, acquire_chain_locks
from fetch import Fetcher, normalized, units, number
from validate import balance_checks, pool_daily_checks
from tornado import full_logs, maybe_pool

A = "0x" + "a" * 40
B = "0x" + "b" * 40


class AccountingTests(unittest.TestCase):
    def test_failed_external_still_costs_gas(self):
        tx = normalized({"from": A, "to": B, "value": "100", "gasUsed": "21000", "gasPrice": "5", "isError": "1"}, "txlist", A, "ETH", "fixture")
        self.assertEqual(tx["amount_raw"], "0")
        self.assertEqual(tx["fee_raw"], "105000")

    def test_self_transfer_only_costs_fee(self):
        tx = normalized({"from": A, "to": A, "value": "100", "gasUsed": "2", "gasPrice": "5"}, "txlist", A, "ETH", "fixture")
        document = {"chain": "eth", "txs": [tx], "coverage": {"complete": True, "to_block": 0}, "balance_now": [{"asset": "ETH", "symbol": "ETH", "decimals": 18, "amount_raw": "0", "block": 0, "raw_ref": "fixture"}]}
        self.assertEqual(balance_checks(document)[0]["difference_raw"], "-10")

    def test_wrapped_native_adjustment_keeps_raw_difference(self):
        token = "0x" + "c" * 40
        doc = {"chain": "eth", "address": A, "txs": [{"asset": token, "direction": "out", "amount_raw": "10"}], "coverage": {"complete": True, "to_block": 5},
               "balance_now": [{"asset": token, "symbol": "WETH", "decimals": 18, "amount_raw": "0", "block": 5, "raw_ref": "fixture"}]}
        cause = {"kind": "weth_supply_events", "to_block": 5, "balance_now_raw": "0", "explanation": "Deposit mint", "correction_raw": "10", "adjusted_expected_raw": "0", "adjusted_match": True}
        checks = balance_checks(doc, {("eth", A, token): [(cause, "fixture")]})
        self.assertEqual(checks[0]["difference_raw"], "-10")
        self.assertTrue(checks[0]["explained"])
        cause["to_block"] = 4
        self.assertNotIn("explained", balance_checks(doc, {("eth", A, token): [(cause, "fixture")]})[0])

    def test_internal_has_no_second_gas_fee(self):
        tx = normalized({"from": B, "to": A, "value": "9", "gasUsed": "1000", "gasPrice": "10"}, "txlistinternal", A, "ETH", "fixture")
        self.assertEqual((tx["amount_raw"], tx["fee_raw"]), ("9", "0"))

    def test_daily_pool_check_uses_block_end_and_preserves_unknown(self):
        doc = {"pool_validation": {"asset": A}, "log_coverage": {"to_block": 8, "complete": True},
               "txs": [{"block": 5, "kind": "pool_deposit", "amount_raw": "10"}, {"block": 8, "kind": "pool_withdrawal", "amount_raw": "10"}],
               "daily_balance": [{"date": "2020-01-01", "block": 4, "assets": []},
                                 {"date": "2020-01-02", "block": 5, "raw_ref": "fixture", "assets": [{"asset": A, "amount_raw": "12", "rpc_response_id": 0}]},
                                 {"date": "2020-01-03", "block": 8, "assets": [{"asset": A, "amount_raw": "0", "rpc_response_id": 0}]},
                                 {"date": "2020-01-04", "block": 9, "assets": []}]}
        result = pool_daily_checks(doc)
        self.assertEqual(result["counts"], {"underlying_asset_not_observed": 1, "above_principal": 1, "match": 1, "beyond_event_history": 1})
        self.assertEqual(result["first_differences"][0]["difference_raw"], "2")

    def test_contract_creation_recipient(self):
        tx = normalized({"from": B, "to": "", "contractAddress": A, "value": "9"}, "txlist", A, "ETH", "fixture")
        self.assertEqual(tx["direction"], "in")

    def test_exact_large_and_negative_units(self):
        self.assertEqual(units(10 ** 80 + 1, 18), "1" + "0" * 62 + ".000000000000000001")
        self.assertEqual(units(-10, 6), "-0.00001")
        self.assertEqual(units(10, 0), "10")

    def test_out_of_range_spam_integer_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "uint256"):
            number("9" * 5000)
        with self.assertRaisesRegex(ValueError, "uint256"):
            number("0x" + "f" * 1024)

    def test_block_boundary_refetched_without_loss(self):
        fetcher = Fetcher(None)
        calls = []
        def explorer(chain, provider, action, **params):
            calls.append(params["startblock"])
            return ([{"blockNumber": "1"}] * 9999 + [{"blockNumber": "2"}] if params["startblock"] == 0 else [{"blockNumber": "2"}, {"blockNumber": "3"}]), "fixture"
        fetcher.explorer = explorer
        rows, refs, gap = fetcher.history("eth", A, "tokentx", 0, 10, "etherscan")
        self.assertEqual(calls, [0, 2])
        self.assertEqual(len(rows), 10001)
        self.assertIsNone(gap)

    def test_single_block_overflow_is_explicit_gap(self):
        fetcher = Fetcher(None)
        fetcher.explorer = lambda *a, **kw: ([{"blockNumber": "0"}] * 10000, "fixture")
        rows, refs, gap = fetcher.history("eth", A, "tokentx", 0, 10, "etherscan")
        self.assertIn("single block", gap["reason"].lower())

    def test_single_block_pages_then_continues_later_blocks(self):
        fetcher = Fetcher(None)
        def explorer(*args, **params):
            if params["startblock"] == 0:
                return [{"blockNumber": "0"}] * (1000 if params["endblock"] != 0 or params["page"] == 1 else 3), "fixture"
            return [{"blockNumber": "2"}], "fixture"
        fetcher.explorer = explorer
        rows, refs, gap = fetcher.history("eth", A, "tokentx", 0, 10, "etherscan")
        self.assertEqual(len(rows), 1004)
        self.assertIsNone(gap)

    def test_query_timeout_splits_block_range_and_finishes(self):
        fetcher = Fetcher(None)
        def explorer(*args, **params):
            if params["endblock"] - params["startblock"] > 5:
                raise APIError("Query Timeout occurred; select a smaller result dataset", "fixture")
            return [{"blockNumber": str(params["startblock"])}], "fixture"
        fetcher.explorer = explorer
        rows, refs, gap = fetcher.history("eth", A, "txlist", 0, 20, "etherscan")
        self.assertGreater(len(rows), 1)
        self.assertIsNone(gap)

    def test_etherscan_null_result_preserves_timeout_message(self):
        client = Client()
        client.request = Mock(return_value=({"status": "0", "message": "Unexpected error, timeout or server too busy", "result": None}, "fixture"))
        with self.assertRaisesRegex(APIError, "timeout"):
            client.etherscan(137, "txlist", address=A)

    def test_silently_clamped_1000_results_are_not_complete(self):
        fetcher = Fetcher(None)
        calls = []
        def explorer(*args, **params):
            calls.append(params["startblock"])
            return ([{"blockNumber": str(i + 1)} for i in range(1000)] if params["startblock"] == 0 else [{"blockNumber": "1000"}, {"blockNumber": "1001"}]), "fixture"
        fetcher.explorer = explorer
        rows, refs, gap = fetcher.history("eth", A, "txlist", 0, 2000, "etherscan")
        self.assertEqual(calls, [0, 1000])
        self.assertEqual(len(rows), 1001)
        self.assertIsNone(gap)

    def test_oversized_pool_log_range_is_split(self):
        class Fake:
            def rpc(self, url, method, params):
                start, end = int(params[0]["fromBlock"], 16), int(params[0]["toBlock"], 16)
                if end - start > 1:
                    raise APIError("Log response size exceeded", "fixture")
                return [{"blockNumber": hex(start), "logIndex": "0x0"}], "fixture"
        fetcher = Fetcher(Fake())
        logs, completed, missing = full_logs(fetcher, A, 0, 7, ["topic"])
        self.assertEqual(len(logs), 4)
        self.assertEqual(len(completed), 4)
        self.assertFalse(missing)

    def test_secret_redacted_from_nested_response(self):
        client = Client()
        client.key = "fixture-secret"
        self.assertEqual(client.redact({"nested": ["apikey=fixture-secret"]}), {"nested": ["apikey=REDACTED"]})

    def test_semantic_error_is_preserved_when_retry_succeeds(self):
        with tempfile.TemporaryDirectory() as folder, patch("client.ROOT", Path(folder)), patch("client.RAW", Path(folder) / "raw"):
            first, second = Mock(), Mock()
            first.__enter__ = Mock(return_value=first)
            first.__exit__ = Mock(return_value=False)
            second.__enter__ = Mock(return_value=second)
            second.__exit__ = Mock(return_value=False)
            first.status = second.status = 200
            first.read.return_value = b'{"status":"0","result":"temporary failure"}'
            second.read.return_value = b'{"status":"1","result":[]}'
            with patch("client.urllib.request.urlopen", side_effect=[first, second]) as opener:
                client = Client()
                result, error_ref = client.request("fixture", "https://example.invalid/data")
                result, success_ref = client.request("fixture", "https://example.invalid/data")
                result, cached_ref = client.request("fixture", "https://example.invalid/data")
                self.assertEqual(opener.call_count, 2)
            self.assertNotEqual(error_ref, success_ref)
            self.assertEqual(success_ref, cached_ref)
            self.assertEqual(read_json(Path(folder) / error_ref)["response"]["result"], "temporary failure")

    def test_chain_lock_prevents_overlapping_writers(self):
        with tempfile.TemporaryDirectory() as folder, patch("client.RAW", Path(folder)):
            first = acquire_chain_locks(["eth"])
            try:
                with self.assertRaisesRegex(RuntimeError, "chain eth"):
                    acquire_chain_locks(["eth"])
                other = acquire_chain_locks(["bsc"])
                for handle in other:
                    handle.close()
            finally:
                for handle in first:
                    handle.close()

    def test_blockscout_v2_cursor_and_actual_fee(self):
        class Fake:
            def request(self, source, url, params, **kwargs):
                block = 8 if not params else 7
                item = {"block_number": block, "hash": "h" + str(block), "timestamp": "2024-01-01T00:00:00Z", "from": {"hash": A}, "to": {"hash": B}, "value": "3", "fee": {"value": "13"}, "gas_used": "2", "gas_price": "5", "l1_fee": "7", "status": "ok"}
                return {"items": [item], "next_page_params": {"block_number": 8} if block == 8 else None}, "fixture"
        fetcher = Fetcher(Fake())
        rows, refs, gap = fetcher.history_v2("op", A, "txlist", 0, 10)
        self.assertEqual(len(rows), 2)
        self.assertIsNone(gap)
        tx = normalized(rows[0][0], "txlist", A, "ETH", rows[0][1])
        self.assertEqual(tx["fee_raw"], "20")

    def test_completed_rerun_does_not_query_history(self):
        with tempfile.TemporaryDirectory() as folder, patch("fetch.ROOT", Path(folder)):
            prior = {"chain": "eth", "address": A, "fetch_schema_version": 2, "coverage": {"complete": True, "from_block": 0, "to_block": 10}, "txs": [], "balance_now": []}
            save_json(Path(folder) / f"data/timelines/eth/{A}.json.gz", prior)
            fetcher = Fetcher(None)
            fetcher.heads["eth"] = {"block": 11, "time_utc": "2024-01-01T00:00:00Z"}
            fetcher.snapshots["eth", A] = {"balance": "0x0", "nonce": "0x0", "code": "0x", "raw_ref": "fixture", "batch_index": 0}
            fetcher.providers["eth"] = "etherscan"
            fetcher.history = Mock(side_effect=AssertionError("completed history was queried"))
            fetcher.balances = lambda *args: ([], [])
            result = fetcher.fetch_address("eth", A, {"listed_chains": ["eth"], "dates": [], "input_raw_refs": []})
            self.assertEqual(result["coverage"]["to_block"], 10)
            fetcher.history.assert_not_called()

    def test_refresh_queries_only_new_blocks(self):
        with tempfile.TemporaryDirectory() as folder, patch("fetch.ROOT", Path(folder)):
            prior = {"chain": "eth", "address": A, "fetch_schema_version": 2, "coverage": {"complete": True, "from_block": 0, "to_block": 10, "actions": {}}, "txs": [], "balance_now": []}
            save_json(Path(folder) / f"data/timelines/eth/{A}.json.gz", prior)
            fetcher = Fetcher(None)
            fetcher.heads["eth"] = {"block": 11, "time_utc": "2024-01-01T00:00:00Z"}
            fetcher.snapshots["eth", A] = {"balance": "0x0", "nonce": "0x0", "code": "0x", "raw_ref": "fixture", "batch_index": 0}
            fetcher.providers["eth"] = "etherscan"
            fetcher.history = Mock(return_value=([], [], None))
            fetcher.balances = lambda *args: ([], [])
            fetcher.fetch_address("eth", A, {"listed_chains": ["eth"], "dates": [], "input_raw_refs": []}, refresh=True)
            self.assertEqual(fetcher.history.call_count, 3)
            self.assertTrue(all(call.args[3:5] == (11, 11) for call in fetcher.history.call_args_list))


if __name__ == "__main__":
    unittest.main()
