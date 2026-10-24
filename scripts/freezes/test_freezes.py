"""Focused ABI/units tests; the full offline evidence check is fetch_freezes --check."""
import unittest

from fetch_freezes import TOPICS, TRC20, USDC, USDT, decode, integer, replay_blacklists, tron_address, units


class EventDecodingTests(unittest.TestCase):
    def row(self, token, event, topics, data):
        scan = dict(chain="ETH", token=token, event=event, from_block=1, to_block=1)
        log = dict(address=USDT if token == "USDT" else USDC, topics=topics, data=data,
                   blockNumber="0x1", timeStamp="0x0", transactionHash="0x" + "ab" * 32,
                   transactionIndex="0x", logIndex="0x0")
        return list(decode(scan, {"response": {"result": [log]}}, "fixture"))[0]

    def test_tether_nonindexed_address_and_exact_burn_units(self):
        address = "1234567890abcdef1234567890abcdef12345678"
        row = self.row("USDT", "DestroyedBlackFunds", [TOPICS["DestroyedBlackFunds"]],
                       "0x" + address.rjust(64, "0") + hex(1234567890123456789)[2:].rjust(64, "0"))
        self.assertEqual(row["address_normalized"], "0x" + address)
        self.assertEqual(row["amount"], "1234567890123.456789")
        self.assertEqual(row["amount_raw"], "1234567890123456789")
        # A later burn must never be labelled as a freeze-time balance.
        self.assertEqual(row["balance_at_freeze"], "")

    def test_circle_indexed_address(self):
        address = "1234567890abcdef1234567890abcdef12345678"
        row = self.row("USDC", "Blacklisted", [TOPICS["Blacklisted"], "0x" + address.rjust(64, "0"), None], "0x")
        self.assertEqual(row["address_normalized"], "0x" + address)
        self.assertEqual(row["amount"], "")
        self.assertEqual(row["transaction_index"], 0)

    def test_wrong_contract_and_topic_fail(self):
        with self.assertRaises(AssertionError):
            self.row("USDT", "AddedBlackList", [TOPICS["Blacklisted"]], "0x" + "0" * 64)

    def test_tron_base58_checksum_and_prefix(self):
        self.assertEqual(tron_address("0xa614f803b6fd780986a42c78ec9c7f77e6ded13c")[0], TRC20)
        self.assertEqual(tron_address("41a614f803b6fd780986a42c78ec9c7f77e6ded13c")[0], TRC20)
        with self.assertRaises(ValueError):
            tron_address("421234567890abcdef1234567890abcdef12345678")

    def test_exact_decimal_and_index_zero(self):
        self.assertEqual(units(1), "0.000001")
        self.assertEqual(units(0), "0")
        self.assertEqual(integer("0x"), 0)
        self.assertEqual(units(2**256-1), "115792089237316195423570985008687907853269984665640564039457584007913129.639935")

    def test_readdition_restores_membership_and_burn_does_not_clear(self):
        events = ["AddedBlackList", "RemovedBlackList", "AddedBlackList", "DestroyedBlackFunds"]
        rows = [dict(chain="ETH", token="USDT", address="address-a", event=event) for event in events]
        active, touched = replay_blacklists(rows)
        self.assertEqual(active[("ETH", "USDT")], {"address-a"})
        self.assertEqual(touched[("ETH", "USDT")], {"address-a"})
        rows.append(dict(chain="ETH", token="USDT", address="address-a", event="RemovedBlackList"))
        self.assertEqual(replay_blacklists(rows)[0][("ETH", "USDT")], set())


if __name__ == "__main__":
    unittest.main()
