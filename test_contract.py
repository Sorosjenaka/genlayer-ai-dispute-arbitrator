"""Offline unit tests for contract.py with a mocked `genlayer` module.

The real GenLayer SDK only exists inside GenVM/Studio, so we inject a minimal
mock into sys.modules before importing the contract. Mocks cover storage
types, message sender, nondet web/LLM, and consensus runners.
"""
import sys
import types
import json
import unittest
from dataclasses import dataclass


def _install_genlayer_mock(llm_responses=None, web_body=b"<html>deliverable</html>", web_status=200):
    llm_responses = llm_responses or {}
    mock = types.ModuleType("genlayer")

    class DynArray(list):
        pass

    class TreeMap(dict):
        def get_or_insert_default(self, key):
            if key not in self:
                self[key] = {}
            return self[key]

    mock.DynArray = DynArray
    mock.TreeMap = TreeMap
    mock.u256 = int
    mock.Address = str

    def allow_storage(cls):
        return cls

    mock.allow_storage = allow_storage

    class _Addr:
        def __init__(self, hx):
            self._hx = hx

        @property
        def as_hex(self):
            return self._hx

        def __str__(self):
            return self._hx

    class _Msg:
        sender_address = _Addr("0xBuyer")

    class _Gl:
        message = _Msg()

        class Contract:
            pass

    mock.gl = _Gl()
    mock.message = _Msg()

    class _Public:
        @staticmethod
        def view(fn):
            fn._gl_public = "view"
            return fn

        @staticmethod
        def write(fn):
            fn._gl_public = "write"
            return fn

    mock.public = _Public

    class UserError(Exception):
        def __init__(self, message=""):
            super().__init__(message)
            self.message = message

    class VMError(Exception):
        pass

    class Return:
        def __init__(self, calldata):
            self.calldata = calldata

    def run_nondet_unsafe(leader_fn, validator_fn):
        try:
            result = leader_fn()
        except (UserError, VMError) as e:
            # leader errored: validator decides; our mock validator returns False -> propagate
            ok = validator_fn(e)
            if not ok:
                raise
            raise
        ok = validator_fn(Return(result))
        if not ok:
            raise UserError("consensus rejected")
        return result

    def strict_eq(fn):
        return fn()

    mock.vm = types.SimpleNamespace(UserError=UserError, VMError=VMError, Return=Return,
                                    run_nondet_unsafe=run_nondet_unsafe, run_nondet=run_nondet_unsafe)
    mock.eq_principle = types.SimpleNamespace(strict_eq=strict_eq)

    class _Resp:
        def __init__(self, body, status):
            self.body = body
            self.status = status

    def _web_get(url):
        return _Resp(web_body, web_status)

    state = {"calls": []}

    def _exec_prompt(prompt):
        state["calls"].append(prompt)
        if "neutral on-chain arbitrator" in prompt:
            return llm_responses.get("arbitrate", json.dumps({
                "ruling": "RELEASE_SELLER", "confidence": 85,
                "reasoning": "Work matches terms."}))
        return llm_responses.get("verify", json.dumps({
            "verdict": "APPROVED", "score": 90,
            "reasoning": "Deliverable satisfies terms."}))

    mock.nondet = types.SimpleNamespace(
        web=types.SimpleNamespace(get=_web_get),
        exec_prompt=_exec_prompt,
    )
    # also expose under gl namespace like real SDK (gl.nondet / gl.vm / gl.eq_principle)
    mock.gl.nondet = mock.nondet
    mock.gl.vm = mock.vm
    mock.gl.eq_principle = mock.eq_principle
    mock.gl.public = mock.public
    mock.gl.storage = types.SimpleNamespace(copy_to_memory=lambda x: x)
    mock.storage = mock.gl.storage

    sys.modules["genlayer"] = mock
    return mock, state


MOCK, MOCK_STATE = _install_genlayer_mock()

from contract import MilestoneEscrowArbiter  # noqa: E402


def _new_contract(buyer="0xBuyer"):
    MOCK.gl.message.sender_address = type("A", (), {"as_hex": buyer})()
    MOCK.message.sender_address = MOCK.gl.message.sender_address
    c = MilestoneEscrowArbiter()
    # emulate GenVM zero-init for storage maps
    from genlayer import TreeMap, DynArray
    c.escrows = TreeMap()
    c.escrow_ids = DynArray()
    c.next_id = 0
    c.owner = buyer
    return c


def _as(sender, fn, *args, **kwargs):
    MOCK.gl.message.sender_address = type("A", (), {"as_hex": sender})()
    MOCK.message.sender_address = MOCK.gl.message.sender_address
    return fn(*args, **kwargs)


class TestLifecycle(unittest.TestCase):
    def test_create_fund_submit_release_happy_path(self):
        c = _new_contract("0xBuyer")
        eid = _as("0xBuyer", c.create_escrow, "0xSeller", "Build landing page with contact form", 1000)
        self.assertEqual(eid, "0")
        self.assertEqual(_as("0xBuyer", c.fund_escrow, eid), "FUNDED")
        self.assertEqual(_as("0xSeller", c.submit_deliverable, eid, "https://example.com/work", "done"), "SUBMITTED")
        status = _as("0xAnyone", c.verify_deliverable, eid)
        self.assertEqual(status, "VERIFIED_APPROVED")
        esc = _as("0xAnyone", c.get_escrow, eid)
        self.assertEqual(esc["verdict"], "APPROVED")
        self.assertGreaterEqual(esc["score"], 70)
        self.assertEqual(_as("0xBuyer", c.release, eid), "RESOLVED_SELLER")

    def test_create_validation(self):
        c = _new_contract()
        with self.assertRaises(Exception):
            _as("0xBuyer", c.create_escrow, "", "Valid terms here xx", 10)
        with self.assertRaises(Exception):
            _as("0xBuyer", c.create_escrow, "0xSeller", "short", 10)
        with self.assertRaises(Exception):
            _as("0xBuyer", c.create_escrow, "0xSeller", "Valid terms here xx", 0)

    def test_only_buyer_can_fund(self):
        c = _new_contract("0xBuyer")
        eid = _as("0xBuyer", c.create_escrow, "0xSeller", "Build landing page with contact form", 100)
        with self.assertRaises(Exception):
            _as("0xEve", c.fund_escrow, eid)

    def test_only_seller_can_submit(self):
        c = _new_contract("0xBuyer")
        eid = _as("0xBuyer", c.create_escrow, "0xSeller", "Build landing page with contact form", 100)
        _as("0xBuyer", c.fund_escrow, eid)
        with self.assertRaises(Exception):
            _as("0xBuyer", c.submit_deliverable, eid, "https://example.com/x", "hi")

    def test_rejected_path_refund(self):
        import genlayer as gl_live
        orig_prompt = gl_live.nondet.exec_prompt

        def rejected_prompt(prompt):
            if "neutral on-chain arbitrator" in prompt:
                return orig_prompt(prompt)
            return json.dumps({"verdict": "REJECTED", "score": 10,
                               "reasoning": "Empty page, nothing delivered."})

        gl_live.nondet.exec_prompt = rejected_prompt
        try:
            c = _new_contract("0xBuyer")
            eid = _as("0xBuyer", c.create_escrow, "0xSeller", "Build landing page with contact form", 100)
            _as("0xBuyer", c.fund_escrow, eid)
            _as("0xSeller", c.submit_deliverable, eid, "https://example.com/empty", "done")
            status = _as("0xAnyone", c.verify_deliverable, eid)
            self.assertEqual(status, "VERIFIED_REJECTED")
            self.assertEqual(_as("0xBuyer", c.refund, eid), "RESOLVED_BUYER")
        finally:
            gl_live.nondet.exec_prompt = orig_prompt

    def test_dispute_and_arbitrate(self):
        c = _new_contract("0xBuyer")
        eid = _as("0xBuyer", c.create_escrow, "0xSeller", "Build landing page with contact form", 500)
        _as("0xBuyer", c.fund_escrow, eid)
        _as("0xSeller", c.submit_deliverable, eid, "https://example.com/work", "done")
        _as("0xAnyone", c.verify_deliverable, eid)
        self.assertEqual(_as("0xBuyer", c.raise_dispute, eid, "Missing contact form section", ""), "DISPUTED")
        status = _as("0xAnyone", c.arbitrate_dispute, eid)
        self.assertIn(status, ("RESOLVED_SELLER", "RESOLVED_BUYER", "RESOLVED_SPLIT"))
        stats = _as("0xAnyone", c.get_stats)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["resolved"], 1)

    def test_split_even_amount(self):
        c = _new_contract("0xBuyer")
        eid = _as("0xBuyer", c.create_escrow, "0xSeller", "Build landing page with contact form", 1000)
        c.escrows[eid].status = "RESOLVED_SPLIT"
        result = _as("0xSeller", c.split, eid)
        self.assertIn("buyer=500", result.lower())
        self.assertIn("seller=500", result.lower())
        self.assertEqual(c.escrows[eid].status, "RESOLVED_SPLIT_EXECUTED")

    def test_split_odd_amount_buyer_gets_remainder(self):
        c = _new_contract("0xBuyer")
        eid = _as("0xBuyer", c.create_escrow, "0xSeller", "Build landing page with contact form", 1001)
        c.escrows[eid].status = "RESOLVED_SPLIT"
        result = _as("0xBuyer", c.split, eid)
        self.assertIn("buyer=501", result.lower())
        self.assertIn("seller=500", result.lower())

    def test_split_rejected_without_split_ruling(self):
        c = _new_contract("0xBuyer")
        eid = _as("0xBuyer", c.create_escrow, "0xSeller", "Build landing page with contact form", 100)
        with self.assertRaises(Exception):
            _as("0xBuyer", c.split, eid)

    def test_split_rejected_for_outsider(self):
        c = _new_contract("0xBuyer")
        eid = _as("0xBuyer", c.create_escrow, "0xSeller", "Build landing page with contact form", 100)
        c.escrows[eid].status = "RESOLVED_SPLIT"
        with self.assertRaises(Exception):
            _as("0xEve", c.split, eid)

    def test_split_single_use(self):
        c = _new_contract("0xBuyer")
        eid = _as("0xBuyer", c.create_escrow, "0xSeller", "Build landing page with contact form", 100)
        c.escrows[eid].status = "RESOLVED_SPLIT"
        _as("0xBuyer", c.split, eid)
        with self.assertRaises(Exception):
            _as("0xBuyer", c.split, eid)

    def test_views(self):
        c = _new_contract("0xBuyer")
        eid = _as("0xBuyer", c.create_escrow, "0xSeller", "Build landing page with contact form", 50)
        lst = _as("0xAnyone", c.list_escrows)
        self.assertIn(eid, lst)
        stats = _as("0xAnyone", c.get_stats)
        self.assertEqual(stats["total"], 1)


if __name__ == "__main__":
    unittest.main()
