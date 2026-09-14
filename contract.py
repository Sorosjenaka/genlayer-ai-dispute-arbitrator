# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""
MilestoneEscrowArbiter  -  AI-arbitrated milestone escrow for GenLayer.

Use case (why this matters beyond a demo):
Freelance / agentic-commerce deals constantly stall on "was the deliverable
actually done?". This contract is a reusable primitive: lock terms on-chain,
let the seller link a deliverable URL, and let GenLayer validators  -  each
running a different LLM, each fetching the URL independently  -  reach consensus
on whether the work satisfies the terms. A second, separate arbitration pass
resolves disputes with its own ruling + confidence.

How consensus is used (read this before reviewing):
1. `verify_deliverable`  -  leader fetches `deliverable_url` via
   `gl.nondet.web.get`, feeds page text + `terms` to `gl.nondet.exec_prompt`,
   and returns {verdict, score, reasoning}. Validators RE-RUN the same
   fetch+prompt independently and accept only if:
     - `verdict` matches exactly (APPROVED | NEEDS_REVISION | REJECTED), and
     - `score` (0-100) differs by at most 15.
   `reasoning` is stored but NEVER compared (two LLMs word things
   differently  -  comparing it would break consensus for no security gain).
2. `arbitrate_dispute`  -  same pattern, different question: given terms +
   deliverable + dispute reason + prior verdict, return
   {ruling: RELEASE_SELLER | REFUND_BUYER | SPLIT, confidence, reasoning}.
   Validators re-run and require exact `ruling` match + confidence within 20.
   SPLIT is gated: both sides must independently conclude SPLIT.
3. `check_deliverable_reachable`  -  uses `gl.eq_principle.strict_eq` because
   the answer is a deterministic bool (HTTP 200 or not), canonicalized before
   comparison. This shows when strict_eq is correct vs. when a custom
   validator is required.

State design:
- `escrows: TreeMap[str, Escrow]`  -  one record per deal, keyed by string id.
- `escrow_ids: DynArray[str]`  -  insertion-order index for listing.
- `next_id: u256`  -  monotonic counter, never reused.
- `owner: str`  -  deployer address (hex), for stats/admin clarity.
"""

from genlayer import *
from dataclasses import dataclass
import json


def _sender_hex() -> str:
    try:
        return gl.message.sender_address.as_hex
    except Exception:
        try:
            return str(gl.message.sender_address)
        except Exception:
            return "0x0"


def _parse_llm_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


@allow_storage
@dataclass
class Escrow:
    escrow_id: str
    buyer: str
    seller: str
    terms: str
    amount: u256
    deliverable_url: str
    deliverable_note: str
    status: str
    verdict: str
    score: u256
    reasoning: str
    dispute_reason: str
    dispute_evidence_url: str
    ruling: str
    confidence: u256


class MilestoneEscrowArbiter(gl.Contract):
    escrows: TreeMap[str, Escrow]
    escrow_ids: DynArray[str]
    next_id: u256
    owner: str

    def __init__(self):
        self.next_id = 0
        try:
            self.owner = _sender_hex()
        except Exception:
            self.owner = "0x0"

    # ---------- lifecycle ----------

    @gl.public.write
    def create_escrow(self, seller: str, terms: str, amount: u256) -> str:
        if len(seller.strip()) == 0:
            raise gl.vm.UserError("seller address required")
        if len(terms.strip()) < 10:
            raise gl.vm.UserError("terms too short: describe the work (min 10 chars)")
        if amount <= 0:
            raise gl.vm.UserError("amount must be > 0")
        buyer = _sender_hex()
        if buyer.lower() == seller.strip().lower():
            raise gl.vm.UserError("buyer and seller must differ")

        escrow_id = str(self.next_id)
        self.escrows[escrow_id] = Escrow(
            escrow_id=escrow_id,
            buyer=buyer,
            seller=seller.strip(),
            terms=terms.strip(),
            amount=amount,
            deliverable_url="",
            deliverable_note="",
            status="CREATED",
            verdict="NONE",
            score=0,
            reasoning="",
            dispute_reason="",
            dispute_evidence_url="",
            ruling="NONE",
            confidence=0,
        )
        self.escrow_ids.append(escrow_id)
        self.next_id = self.next_id + 1
        return escrow_id

    @gl.public.write
    def fund_escrow(self, escrow_id: str) -> str:
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("escrow not found")
        escrow = self.escrows[escrow_id]
        if escrow.status != "CREATED":
            raise gl.vm.UserError("only CREATED escrows can be funded")
        caller = _sender_hex()
        if caller.lower() != escrow.buyer.lower():
            raise gl.vm.UserError("only buyer can fund")
        escrow.status = "FUNDED"
        self.escrows[escrow_id] = escrow
        return "FUNDED"

    @gl.public.write
    def submit_deliverable(self, escrow_id: str, deliverable_url: str, note: str) -> str:
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("escrow not found")
        escrow = self.escrows[escrow_id]
        if escrow.status not in ("FUNDED", "SUBMITTED", "VERIFIED_REVISION"):
            raise gl.vm.UserError("escrow not awaiting deliverable")
        caller = _sender_hex()
        if caller.lower() != escrow.seller.lower():
            raise gl.vm.UserError("only seller can submit deliverable")
        if not deliverable_url.startswith("http"):
            raise gl.vm.UserError("deliverable_url must start with http")
        escrow.deliverable_url = deliverable_url.strip()
        escrow.deliverable_note = note.strip()[:2000]
        escrow.status = "SUBMITTED"
        escrow.verdict = "NONE"
        escrow.ruling = "NONE"
        self.escrows[escrow_id] = escrow
        return "SUBMITTED"

    # ---------- consensus 1: deliverable verification ----------

    @gl.public.write
    def check_deliverable_reachable(self, escrow_id: str) -> str:
        """Deterministic pre-check (strict_eq): is the deliverable URL fetchable?"""
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("escrow not found")
        escrow = gl.storage.copy_to_memory(self.escrows[escrow_id])
        url = str(escrow.deliverable_url)
        if len(url) == 0:
            raise gl.vm.UserError("no deliverable submitted yet")

        def _fetch() -> str:
            try:
                response = gl.nondet.web.get(url)
                code = int(response.status)
                ok = code >= 200 and code < 400
                return json.dumps({"reachable": ok}, sort_keys=True)
            except Exception:
                return json.dumps({"reachable": False}, sort_keys=True)

        result = json.loads(gl.eq_principle.strict_eq(_fetch))
        return "REACHABLE" if result.get("reachable") else "UNREACHABLE"

    @gl.public.write
    def verify_deliverable(self, escrow_id: str) -> str:
        """
        Core AI consensus: does the deliverable satisfy the terms?
        Anyone may call; validators independently re-fetch + re-judge.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("escrow not found")
        escrow_mem = gl.storage.copy_to_memory(self.escrows[escrow_id])
        if escrow_mem.status not in ("SUBMITTED", "VERIFIED_REVISION", "DISPUTED"):
            raise gl.vm.UserError("nothing to verify in current status")
        terms = str(escrow_mem.terms)
        url = str(escrow_mem.deliverable_url)
        note = str(escrow_mem.deliverable_note)

        def leader_fn():
            response = gl.nondet.web.get(url)
            try:
                page = response.body.decode("utf-8")[:12000]
            except Exception:
                page = str(response.body)[:12000]
            prompt = (
                "You are a strict freelance milestone auditor.\n"
                f"AGREED TERMS: {terms}\n"
                f"SELLER NOTE: {note}\n"
                f"DELIVERABLE PAGE CONTENT (truncated): {page}\n\n"
                "Decide ONLY from the deliverable content vs the terms.\n"
                'Return JSON only: {"verdict": "APPROVED"|"NEEDS_REVISION"|"REJECTED", '
                '"score": 0-100 integer, "reasoning": "2-4 sentences citing specifics"}.\n'
                "Score guide: >=70 APPROVED, 40-69 NEEDS_REVISION, <40 REJECTED. "
                "Verdict and score must be consistent."
            )
            raw = gl.nondet.exec_prompt(prompt)
            data = _parse_llm_json(raw)
            verdict = str(data.get("verdict", "")).strip().upper()
            score = int(data.get("score", 0))
            reasoning = str(data.get("reasoning", ""))[:2000]
            if verdict not in ("APPROVED", "NEEDS_REVISION", "REJECTED"):
                raise gl.vm.UserError("LLM returned invalid verdict")
            if score < 0 or score > 100:
                raise gl.vm.UserError("LLM returned out-of-range score")
            return {"verdict": verdict, "score": score, "reasoning": reasoning}

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            try:
                mine = leader_fn()
            except Exception:
                return False
            try:
                leader_data = leader_result.calldata
            except Exception:
                return False
            if mine.get("verdict") != leader_data.get("verdict"):
                return False
            try:
                diff = abs(int(mine.get("score", 0)) - int(leader_data.get("score", 0)))
            except Exception:
                return False
            return diff <= 15

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        escrow = self.escrows[escrow_id]
        escrow.verdict = result["verdict"]
        escrow.score = result["score"]
        escrow.reasoning = result["reasoning"]
        if result["verdict"] == "APPROVED":
            escrow.status = "VERIFIED_APPROVED"
        elif result["verdict"] == "NEEDS_REVISION":
            escrow.status = "VERIFIED_REVISION"
        else:
            escrow.status = "VERIFIED_REJECTED"
        self.escrows[escrow_id] = escrow
        return escrow.status

    # ---------- disputes ----------

    @gl.public.write
    def raise_dispute(self, escrow_id: str, reason: str, evidence_url: str) -> str:
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("escrow not found")
        escrow = self.escrows[escrow_id]
        if escrow.status in ("RESOLVED_SELLER", "RESOLVED_BUYER", "RESOLVED_SPLIT"):
            raise gl.vm.UserError("already resolved")
        caller = _sender_hex()
        if caller.lower() not in (escrow.buyer.lower(), escrow.seller.lower()):
            raise gl.vm.UserError("only buyer or seller can dispute")
        if len(reason.strip()) < 10:
            raise gl.vm.UserError("dispute reason too short (min 10 chars)")
        escrow.dispute_reason = reason.strip()[:2000]
        escrow.dispute_evidence_url = (evidence_url or "").strip()[:1000]
        escrow.status = "DISPUTED"
        self.escrows[escrow_id] = escrow
        return "DISPUTED"

    @gl.public.write
    def arbitrate_dispute(self, escrow_id: str) -> str:
        """
        Second AI consensus: final ruling on a dispute.
        Considers terms + deliverable + dispute reason + prior verification.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("escrow not found")
        escrow_mem = gl.storage.copy_to_memory(self.escrows[escrow_id])
        if escrow_mem.status != "DISPUTED":
            raise gl.vm.UserError("escrow is not disputed")
        terms = str(escrow_mem.terms)
        url = str(escrow_mem.deliverable_url)
        note = str(escrow_mem.deliverable_note)
        dispute_reason = str(escrow_mem.dispute_reason)
        dispute_evidence = str(escrow_mem.dispute_evidence_url)
        prior = str(escrow_mem.verdict) + "/" + str(escrow_mem.score)

        def leader_fn():
            deliverable_text = ""
            if len(url) > 0 and url.startswith("http"):
                try:
                    response = gl.nondet.web.get(url)
                    try:
                        deliverable_text = response.body.decode("utf-8")[:8000]
                    except Exception:
                        deliverable_text = str(response.body)[:8000]
                except Exception:
                    deliverable_text = "(deliverable fetch failed)"
            evidence_text = ""
            if len(dispute_evidence) > 0 and dispute_evidence.startswith("http"):
                try:
                    response = gl.nondet.web.get(dispute_evidence)
                    try:
                        evidence_text = response.body.decode("utf-8")[:4000]
                    except Exception:
                        evidence_text = str(response.body)[:4000]
                except Exception:
                    evidence_text = "(dispute evidence fetch failed)"
            prompt = (
                "You are a neutral on-chain arbitrator for a freelance escrow.\n"
                f"TERMS: {terms}\n"
                f"DELIVERABLE NOTE: {note}\n"
                f"DELIVERABLE CONTENT: {deliverable_text}\n"
                f"PRIOR AI VERDICT: {prior}\n"
                f"DISPUTE REASON: {dispute_reason}\n"
                f"DISPUTE EVIDENCE CONTENT: {evidence_text}\n\n"
                "Rule: RELEASE_SELLER if work substantially meets terms; "
                "REFUND_BUYER if work missing/broken/off-terms; "
                "SPLIT only if both sides partly right (partial delivery + partial payment fair).\n"
                'Return JSON only: {"ruling": "RELEASE_SELLER"|"REFUND_BUYER"|"SPLIT", '
                '"confidence": 0-100, "reasoning": "3-5 sentences"}.'
            )
            raw = gl.nondet.exec_prompt(prompt)
            data = _parse_llm_json(raw)
            ruling = str(data.get("ruling", "")).strip().upper()
            confidence = int(data.get("confidence", 0))
            reasoning = str(data.get("reasoning", ""))[:2000]
            if ruling not in ("RELEASE_SELLER", "REFUND_BUYER", "SPLIT"):
                raise gl.vm.UserError("LLM returned invalid ruling")
            if confidence < 0 or confidence > 100:
                raise gl.vm.UserError("LLM returned out-of-range confidence")
            return {"ruling": ruling, "confidence": confidence, "reasoning": reasoning}

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            try:
                mine = leader_fn()
            except Exception:
                return False
            try:
                leader_data = leader_result.calldata
            except Exception:
                return False
            if mine.get("ruling") != leader_data.get("ruling"):
                return False
            try:
                diff = abs(int(mine.get("confidence", 0)) - int(leader_data.get("confidence", 0)))
            except Exception:
                return False
            return diff <= 20

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        escrow = self.escrows[escrow_id]
        escrow.ruling = result["ruling"]
        escrow.confidence = result["confidence"]
        escrow.reasoning = result["reasoning"]
        if result["ruling"] == "RELEASE_SELLER":
            escrow.status = "RESOLVED_SELLER"
        elif result["ruling"] == "REFUND_BUYER":
            escrow.status = "RESOLVED_BUYER"
        else:
            escrow.status = "RESOLVED_SPLIT"
        self.escrows[escrow_id] = escrow
        return escrow.status

    # ---------- settlement (deterministic, based on consensus outcomes) ----------

    @gl.public.write
    def release(self, escrow_id: str) -> str:
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("escrow not found")
        escrow = self.escrows[escrow_id]
        if escrow.status not in ("VERIFIED_APPROVED", "RESOLVED_SELLER"):
            raise gl.vm.UserError("release allowed only after APPROVED verification or SELLER ruling")
        caller = _sender_hex()
        if caller.lower() != escrow.buyer.lower():
            raise gl.vm.UserError("only buyer releases")
        escrow.status = "RESOLVED_SELLER"
        self.escrows[escrow_id] = escrow
        return "RESOLVED_SELLER"

    @gl.public.write
    def refund(self, escrow_id: str) -> str:
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("escrow not found")
        escrow = self.escrows[escrow_id]
        if escrow.status not in ("VERIFIED_REJECTED", "RESOLVED_BUYER"):
            raise gl.vm.UserError("refund allowed only after REJECTED verification or BUYER ruling")
        caller = _sender_hex()
        if caller.lower() not in (escrow.buyer.lower(), escrow.seller.lower()):
            raise gl.vm.UserError("only parties can settle")
        escrow.status = "RESOLVED_BUYER"
        self.escrows[escrow_id] = escrow
        return "RESOLVED_BUYER"

    # ---------- views ----------

    @gl.public.view
    def get_escrow(self, escrow_id: str) -> dict:
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("escrow not found")
        escrow = self.escrows[escrow_id]
        return {
            "escrow_id": escrow.escrow_id,
            "buyer": escrow.buyer,
            "seller": escrow.seller,
            "terms": escrow.terms,
            "amount": int(escrow.amount),
            "deliverable_url": escrow.deliverable_url,
            "deliverable_note": escrow.deliverable_note,
            "status": escrow.status,
            "verdict": escrow.verdict,
            "score": int(escrow.score),
            "reasoning": escrow.reasoning,
            "dispute_reason": escrow.dispute_reason,
            "ruling": escrow.ruling,
            "confidence": int(escrow.confidence),
        }

    @gl.public.view
    def list_escrows(self) -> dict:
        out: dict = {}
        for escrow_id in self.escrow_ids:
            escrow = self.escrows[escrow_id]
            out[escrow_id] = {
                "buyer": escrow.buyer,
                "seller": escrow.seller,
                "status": escrow.status,
                "verdict": escrow.verdict,
                "score": int(escrow.score),
                "ruling": escrow.ruling,
            }
        return out

    @gl.public.view
    def get_stats(self) -> dict:
        total = 0
        resolved = 0
        for escrow_id in self.escrow_ids:
            total += 1
            status = self.escrows[escrow_id].status
            if status in ("RESOLVED_SELLER", "RESOLVED_BUYER", "RESOLVED_SPLIT"):
                resolved += 1
        return {"total": total, "resolved": resolved, "owner": self.owner}
