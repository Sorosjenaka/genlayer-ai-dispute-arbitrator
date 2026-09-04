import unittest
from contract import DisputeEscrowContract
from genlayer import MockGenLayerEnvironment


class TestDisputeEscrowContract(unittest.TestCase):
    
    def setUp(self):
        self.env = MockGenLayerEnvironment()
        self.contract = DisputeEscrowContract(
            buyer="0xBuyer",
            seller="0xSeller",
            terms="Deliver code by Friday.",
            amount_usdc=1000
        )
    
    def test_initial_state(self):
        self.assertEqual(self.contract.status, "LOCKED")
        self.assertEqual(self.contract.buyer, "0xBuyer")
        self.assertEqual(self.contract.amount_usdc, 1000)
        self.assertEqual(self.contract.evidence, {"buyer": [], "seller": []})
        self.assertIsNone(self.contract.arbiter_ruling)
    
    def test_deposit_funds_in_locked_state(self):
        result = self.contract.deposit_funds()
        self.assertIn("Escrow active", result)
        self.assertIn("1000 USDC", result)
    
    def test_deposit_funds_fails_in_disputed_state(self):
        self.contract.status = "DISPUTED"
        result = self.contract.deposit_funds()
        self.assertIn("Error", result)
    
    def test_submit_evidence_buyer(self):
        result = self.contract.submit_evidence("buyer", "Payment was made but no delivery.")
        self.assertIn("Evidence submitted", result)
        self.assertEqual(len(self.contract.evidence["buyer"]), 1)
    
    def test_submit_evidence_seller(self):
        result = self.contract.submit_evidence("seller", "Code was delivered on time.")
        self.assertIn("Evidence submitted", result)
        self.assertEqual(len(self.contract.evidence["seller"]), 1)
    
    def test_submit_evidence_invalid_party(self):
        result = self.contract.submit_evidence("invalid", "Evidence")
        self.assertIn("Error", result)
    
    def test_submit_evidence_empty_text(self):
        result = self.contract.submit_evidence("buyer", "")
        self.assertIn("Error", result)
    
    def test_submit_evidence_fails_after_resolution(self):
        self.contract.status = "RESOLVED_BUYER"
        result = self.contract.submit_evidence("buyer", "Late evidence")
        self.assertIn("Error", result)
    
    def test_raise_dispute_from_locked(self):
        result = self.contract.raise_dispute()
        self.assertIn("Dispute raised", result)
        self.assertEqual(self.contract.status, "DISPUTED")
    
    def test_raise_dispute_fails_from_disputed(self):
        self.contract.status = "DISPUTED"
        result = self.contract.raise_dispute()
        self.assertIn("Error", result)
    
    def test_release_funds_from_locked(self):
        result = self.contract.release_funds()
        self.assertIn("Seller", result)
        self.assertEqual(self.contract.status, "RESOLVED_SELLER")
    
    def test_release_funds_fails_from_disputed(self):
        self.contract.status = "DISPUTED"
        result = self.contract.release_funds()
        self.assertIn("Error", result)
    
    def test_release_funds_split_ruling(self):
        self.contract.status = "RESOLVED_SPLIT"
        result = self.contract.release_funds()
        self.assertIn("split", result.lower())
        self.assertIn("Buyer=500", result)
        self.assertIn("Seller=500", result)
    
    def test_release_funds_split_with_odd_amount(self):
        self.contract.amount_usdc = 1001
        self.contract.balance = 1001
        self.contract.status = "RESOLVED_SPLIT"
        result = self.contract.release_funds()
        self.assertIn("Buyer=501", result)
        self.assertIn("Seller=500", result)
    
    def test_get_status_initial(self):
        status = self.contract.get_status()
        self.assertEqual(status["status"], "LOCKED")
        self.assertEqual(status["amount_usdc"], 1000)
    
    def test_get_status_with_evidence(self):
        self.contract.submit_evidence("buyer", "Evidence 1")
        status = self.contract.get_status()
        self.assertEqual(status["buyer_evidence_count"], 1)
    
    def test_get_evidence_no_filter(self):
        self.contract.submit_evidence("buyer", "Buyer evidence")
        self.contract.submit_evidence("seller", "Seller evidence")
        evidence = self.contract.get_evidence()
        self.assertEqual(len(evidence["buyer"]), 1)
        self.assertEqual(len(evidence["seller"]), 1)
    
    def test_get_evidence_invalid_party(self):
        result = self.contract.get_evidence("invalid")
        self.assertIn("error", result.lower())
    
    def test_full_happy_path(self):
        self.contract.deposit_funds()
        dispute_result = self.contract.raise_dispute()
        self.assertIn("Dispute raised", dispute_result)
        self.contract.evidence["buyer"].append("Paid but no delivery")
        self.contract.status = "RESOLVED_BUYER"
        release_result = self.contract.release_funds()
        self.assertIn("Buyer", release_result)
    
    def test_full_escrow_to_seller(self):
        self.contract.deposit_funds()
        release_result = self.contract.release_funds()
        self.assertIn("Seller", release_result)
    
    def test_get_terms(self):
        terms = self.contract.get_terms()
        self.assertEqual(terms, "Deliver code by Friday.")


if __name__ == "__main__":
    unittest.main()
