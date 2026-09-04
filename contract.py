# v0.2.16
# {"Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5g93hwfp7jqmwsfhh8jpz09h6"}

import json
import genlayer as gl


class DisputeEscrowContract(gl.Contract):
    # Persistent storage
    buyer: str
    seller: str
    terms: str
    amount_usdc: int
    status: str
    evidence_buyer: str
    evidence_seller: str
    arbiter_ruling: str
    arbitration_reasoning: str
    balance: int
    buyer_evidence_count: int
    seller_evidence_count: int

    def __init__(self, buyer: str, seller: str, terms: str, amount_usdc: int):
        self.buyer = buyer
        self.seller = seller
        self.terms = terms
        self.amount_usdc = amount_usdc
        self.balance = amount_usdc
        self.status = "LOCKED"
        self.evidence_buyer = ""
        self.evidence_seller = ""
        self.arbiter_ruling = ""
        self.arbitration_reasoning = ""
        self.buyer_evidence_count = 0
        self.seller_evidence_count = 0

    @gl.public.write
    def deposit_funds(self) -> str:
        if self.status != "LOCKED":
            return f"Error: Escrow is not in LOCKED state. Current status: {self.status}"
        return f"Escrow active with {self.amount_usdc} USDC. Terms: {self.terms}"

    @gl.public.write
    def submit_evidence(self, party: str, text_evidence: str) -> str:
        if self.status not in ["LOCKED", "DISPUTED"]:
            return f"Error: Cannot submit evidence. Status: {self.status}"

        party_lower = party.lower()
        if party_lower not in ["buyer", "seller"]:
            return f"Error: Invalid party '{party}'. Must be 'buyer' or 'seller'."

        if not text_evidence or len(text_evidence.strip()) == 0:
            return "Error: Evidence text cannot be empty."

        new_piece = text_evidence.strip()
        if party_lower == "buyer":
            if self.evidence_buyer == "":
                self.evidence_buyer = new_piece
            else:
                self.evidence_buyer = self.evidence_buyer + "\n---\n" + new_piece
            self.buyer_evidence_count = self.buyer_evidence_count + 1
            count = self.buyer_evidence_count
        else:
            if self.evidence_seller == "":
                self.evidence_seller = new_piece
            else:
                self.evidence_seller = self.evidence_seller + "\n---\n" + new_piece
            self.seller_evidence_count = self.seller_evidence_count + 1
            count = self.seller_evidence_count

        return f"Evidence submitted for {party_lower}. Total: {count}"

    @gl.public.write
    def raise_dispute(self) -> str:
        if self.status != "LOCKED":
            return f"Error: Dispute can only be raised from LOCKED. Current: {self.status}"
        self.status = "DISPUTED"
        return "Dispute raised. Ready for GenLayer AI Arbitrator Consensus."

    @gl.public.write
    def execute_ai_arbitration(self) -> str:
        if self.status != "DISPUTED":
            return f"Error: Contract is not under dispute. Current: {self.status}"

        buyer_evidence = self.evidence_buyer
        if buyer_evidence == "":
            buyer_evidence = "No evidence submitted by buyer."

        seller_evidence = self.evidence_seller
        if seller_evidence == "":
            seller_evidence = "No evidence submitted by seller."

        prompt = (
            "Analyze the following dispute and render a verdict based on the contract terms.\n"
            "\n"
            f"Contract Terms: {self.terms}\n"
            "\n"
            f"Buyer's Evidence:\n{buyer_evidence}\n"
            "\n"
            f"Seller's Evidence:\n{seller_evidence}\n"
            "\n"
            "You are an autonomous on-chain arbiter. Evaluate the evidence strictly based on the contract terms.\n"
            "Return ONLY valid JSON with this exact format:\n"
            '{"ruling": "BUYER" or "SELLER" or "SPLIT", "reasoning": "Brief explanation"}\n'
            "\n"
            '- Return "BUYER" if seller failed to fulfill terms\n'
            '- Return "SELLER" if seller fulfilled terms\n'
            '- Return "SPLIT" if both parties have valid claims\n'
        )

        try:
            ai_response = gl.exec_prompt(prompt, temperature=0.0, response_format="json")
            parsed = json.loads(ai_response)
            ruling = parsed.get("ruling", "SPLIT")
            ruling = str(ruling).upper()
            reasoning = parsed.get("reasoning", "No reasoning provided")
            if ruling not in ["BUYER", "SELLER", "SPLIT"]:
                ruling = "SPLIT"
        except Exception:
            ruling = "SPLIT"
            reasoning = "Error parsing AI response. Defaulting to SPLIT."

        self.arbitration_reasoning = str(reasoning)
        self.arbiter_ruling = ruling
        self.status = "RESOLVED_" + ruling
        return f"Ruling: {ruling}. Reason: {reasoning}"

    @gl.public.write
    def release_funds(self) -> str:
        if self.status == "LOCKED":
            self.status = "RESOLVED_SELLER"
            return f"Funds released to Seller. Total: {self.amount_usdc} USDC"

        if self.status == "DISPUTED":
            return "Error: Cannot release while DISPUTED. Execute AI arbitration first."

        if self.status == "RESOLVED_BUYER":
            return f"Funds released to Buyer. Total: {self.amount_usdc} USDC"

        if self.status == "RESOLVED_SELLER":
            return f"Funds released to Seller. Total: {self.amount_usdc} USDC"

        if self.status == "RESOLVED_SPLIT":
            split_amount = self.amount_usdc // 2
            remainder = self.amount_usdc % 2
            buyer_amount = split_amount + remainder
            seller_amount = split_amount
            return f"Funds split: Buyer={buyer_amount} USDC, Seller={seller_amount} USDC"

        return f"Funds handled by state: {self.status}"

    @gl.public.view
    def get_status(self) -> dict:
        return {
            "status": self.status,
            "buyer": self.buyer,
            "seller": self.seller,
            "terms": self.terms,
            "amount_usdc": self.amount_usdc,
            "balance": self.balance,
            "buyer_evidence_count": self.buyer_evidence_count,
            "seller_evidence_count": self.seller_evidence_count,
            "arbiter_ruling": self.arbiter_ruling,
            "arbitration_reasoning": self.arbitration_reasoning,
        }

    @gl.public.view
    def get_evidence(self, party: str) -> dict:
        party_lower = party.lower()
        if party_lower == "buyer":
            return {"party": "buyer", "evidence": self.evidence_buyer, "count": self.buyer_evidence_count}
        if party_lower == "seller":
            return {"party": "seller", "evidence": self.evidence_seller, "count": self.seller_evidence_count}
        return {"error": f"Invalid party '{party}'. Must be 'buyer' or 'seller'."}

    @gl.public.view
    def get_all_evidence(self) -> dict:
        return {
            "buyer": {"evidence": self.evidence_buyer, "count": self.buyer_evidence_count},
            "seller": {"evidence": self.evidence_seller, "count": self.seller_evidence_count},
        }

    @gl.public.view
    def get_terms(self) -> str:
        return self.terms


