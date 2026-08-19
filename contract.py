from genlayer import Contract, gl, Result
from typing import Dict, List, Optional
import json

class DisputeEscrowContract(Contract):
    def __init__(self, buyer: str, seller: str, terms: str, amount_usdc: int):
        super().__init__()
        self.buyer: str = buyer
        self.seller: str = seller
        self.terms: str = terms
        self.amount_usdc: int = amount_usdc
        self.status: str = "LOCKED"
        self.evidence: Dict[str, List[str]] = {"buyer": [], "seller": []}
        self.arbiter_ruling: Optional[str] = None
        self.arbitration_reasoning: Optional[str] = None
        self.balance: int = amount_usdc

    @gl.public
    def deposit_funds(self) -> str:
        if self.status != "LOCKED": return "Escrow is not in lockable state."
        return f"Escrow active with {self.amount_usdc} USDC. Terms: {self.terms}"

    @gl.public
    def submit_evidence(self, party: str, text_evidence: str) -> str:
        if self.status not in ["LOCKED", "DISPUTED"]: return "Cannot submit evidence; contract is finalized."
        party = party.lower()
        if party not in ["buyer", "seller"]: return "Invalid party."
        self.evidence[party].append(text_evidence)
        return f"Evidence submitted for {party}."

    @gl.public
    def raise_dispute(self) -> str:
        if self.status != "LOCKED": return "Dispute can only be raised from LOCKED state."
        self.status = "DISPUTED"
        return "Dispute raised. Ready for GenLayer AI Arbitrator Consensus."

    @gl.public
    def execute_ai_arbitration(self) -> str:
        if self.status != "DISPUTED": return "Contract is not under dispute."
        buyer_text = "\n---\n".join(self.evidence["buyer"]) or "No evidence."
        seller_text = "\n---\n".join(self.evidence["seller"]) or "No evidence."
        prompt = f"Analyze terms: {self.terms}\nBuyer: {buyer_text}\nSeller: {seller_text}\nReturn JSON with keys 'ruling' (BUYER/SELLER/SPLIT) and 'reasoning'."
        ai_response = gl.exec_prompt(prompt, temperature=0.0, response_format="json")
        try:
            parsed = json.loads(ai_response)
            ruling = parsed.get("ruling", "SPLIT").upper()
            reasoning = parsed.get("reasoning", "")
        except:
            ruling, reasoning = "SPLIT", "Parse error"
        self.arbitration_reasoning = reasoning
        self.status = f"RESOLVED_{ruling}"
        self.arbiter_ruling = ruling
        return f"Ruling: {ruling}. Reason: {reasoning}"

    @gl.public
    def release_funds(self) -> str:
        if self.status == "LOCKED":
            self.status = "RESOLVED_SELLER"
            return f"Funds released to Seller."
        return f"Funds handled by state: {self.status}"
