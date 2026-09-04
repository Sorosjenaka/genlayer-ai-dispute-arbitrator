from genlayer import Contract, gl, Result
from typing import Dict, List, Optional
import json


class DisputeEscrowContract(Contract):
    """
    AI-Powered Dispute Resolution Escrow Contract for GenLayer.
    Leverages GenLayer's Intelligent Contracts with AI consensus.
    """
    
    def __init__(self, buyer: str, seller: str, terms: str, amount_usdc: int):
        super().__init__()
        
        # Party addresses
        self.buyer: str = buyer
        self.seller: str = seller
        self.terms: str = terms
        self.amount_usdc: int = amount_usdc
        
        # Contract state
        self.status: str = "LOCKED"
        self.evidence: Dict[str, List[str]] = {"buyer": [], "seller": []}
        
        # Arbitration results
        self.arbiter_ruling: Optional[str] = None
        self.arbitration_reasoning: Optional[str] = None
        
        # Fund tracking
        self.balance: int = amount_usdc
        self.created_at: int = 0
        self.disputed_at: Optional[int] = None
        self.resolved_at: Optional[int] = None
    
    @gl.public
    def deposit_funds(self) -> str:
        if self.status != "LOCKED":
            return f"Error: Escrow is not in LOCKED state. Current status: {self.status}"
        return f"Escrow active with {self.amount_usdc} USDC. Terms: {self.terms}"
    
    @gl.public
    def submit_evidence(self, party: str, text_evidence: str) -> str:
        if self.status not in ["LOCKED", "DISPUTED"]:
            return f"Error: Cannot submit evidence. Contract is finalized with status: {self.status}"
        
        party = party.lower()
        if party not in ["buyer", "seller"]:
            return f"Error: Invalid party '{party}'. Must be 'buyer' or 'seller'."
        
        if not text_evidence or len(text_evidence.strip()) == 0:
            return "Error: Evidence text cannot be empty."
        
        self.evidence[party].append(text_evidence.strip())
        return f"Evidence submitted for {party}. Total evidence count: {len(self.evidence[party])}"
    
    @gl.public
    def raise_dispute(self) -> str:
        if self.status != "LOCKED":
            return f"Error: Dispute can only be raised from LOCKED state. Current status: {self.status}"
        
        self.status = "DISPUTED"
        self.disputed_at = 0
        return "Dispute raised. Ready for GenLayer AI Arbitrator Consensus."
    
    @gl.public
    def execute_ai_arbitration(self) -> str:
        """Execute AI arbitration using GenLayer consensus."""
        if self.status != "DISPUTED":
            return f"Error: Contract is not under dispute. Current status: {self.status}"
        
        buyer_evidence = "\n---\n".join(self.evidence["buyer"]) or "No evidence submitted by buyer."
        seller_evidence = "\n---\n".join(self.evidence["seller"]) or "No evidence submitted by seller."
        
        prompt = f"""Analyze the following dispute and render a verdict based on the contract terms.

Contract Terms: {self.terms}

Buyer's Evidence:
{buyer_evidence}

Seller's Evidence:
{seller_evidence}

You are an autonomous on-chain arbiter. Evaluate the evidence strictly based on the contract terms.
Return ONLY valid JSON with this exact format:
{{"ruling": "BUYER" | "SELLER" | "SPLIT", "reasoning": "Brief explanation of the ruling"}}

- "BUYER" if the seller failed to fulfill terms
- "SELLER" if the seller fulfilled terms
- "SPLIT" if both parties have valid claims
"""
        
        try:
            ai_response = gl.exec_prompt(prompt, temperature=0.0, response_format="json")
            parsed = json.loads(ai_response)
            ruling = parsed.get("ruling", "SPLIT").upper()
            reasoning = parsed.get("reasoning", "No reasoning provided")
            
            if ruling not in ["BUYER", "SELLER", "SPLIT"]:
                ruling = "SPLIT"
                
        except (json.JSONDecodeError, KeyError, Exception) as e:
            ruling = "SPLIT"
            reasoning = f"Error parsing AI response: {str(e)}. Defaulting to SPLIT ruling."
        
        self.arbitration_reasoning = reasoning
        self.arbiter_ruling = ruling
        self.status = f"RESOLVED_{ruling}"
        self.resolved_at = 0
        
        return f"Ruling: {ruling}. Reason: {reasoning}"
    
    @gl.public
    def release_funds(self, party: Optional[str] = None) -> str:
        """Release funds based on current contract state."""
        if self.status == "LOCKED":
            self.status = "RESOLVED_SELLER"
            self.resolved_at = 0
            return f"Funds released to Seller. Total: {self.amount_usdc} USDC"
        
        elif self.status == "DISPUTED":
            return f"Error: Cannot release funds while in DISPUTED state. Execute AI arbitration first."
        
        elif self.status.startswith("RESOLVED_"):
            ruling = self.status.replace("RESOLVED_", "")
            
            if ruling == "BUYER":
                return f"Funds released to Buyer. Total: {self.amount_usdc} USDC"
            elif ruling == "SELLER":
                return f"Funds released to Seller. Total: {self.amount_usdc} USDC"
            elif ruling == "SPLIT":
                split_amount = self.amount_usdc // 2
                remainder = self.amount_usdc % 2
                buyer_amount = split_amount + remainder
                seller_amount = split_amount
                return f"Funds split: Buyer={buyer_amount} USDC, Seller={seller_amount} USDC"
        
        return f"Funds handled by state: {self.status}"
    
    @gl.public.view
    def get_status(self) -> Dict:
        """Get the current status of the escrow contract."""
        return {
            "status": self.status,
            "buyer": self.buyer,
            "seller": self.seller,
            "amount_usdc": self.amount_usdc,
            "balance": self.balance,
            "buyer_evidence_count": len(self.evidence["buyer"]),
            "seller_evidence_count": len(self.evidence["seller"]),
            "arbiter_ruling": self.arbiter_ruling,
            "arbitration_reasoning": self.arbitration_reasoning
        }
    
    @gl.public.view
    def get_evidence(self, party: Optional[str] = None) -> Dict:
        """Get evidence submitted by parties."""
        if party is None:
            return self.evidence
        
        party = party.lower()
        if party not in ["buyer", "seller"]:
            return {"error": f"Invalid party '{party}'. Must be 'buyer' or 'seller'."}
        
        return {party: self.evidence[party]}
    
    @gl.public.view
    def get_terms(self) -> str:
        """Get the contract terms."""
        return self.terms
