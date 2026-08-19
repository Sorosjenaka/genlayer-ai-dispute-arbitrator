import unittest
from contract import DisputeEscrowContract
from genlayer import MockGenLayerEnvironment

class TestDisputeEscrowContract(unittest.TestCase):
    def setUp(self):
        self.env = MockGenLayerEnvironment()
        self.contract = DisputeEscrowContract("0xBuyer", "0xSeller", "Deliver code by Friday.", 1000)

    def test_initial_state(self):
        self.assertEqual(self.contract.status, "LOCKED")

if __name__ == "__main__":
    unittest.main()
