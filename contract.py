# v0.2.16
# {"Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5g93hwfp7jqmwsfhh8jpz09h6"}

import genlayer as gl


class DisputeEscrowContract(gl.Contract):
    buyer: str
    seller: str
    terms: str
    amount_usdc: int
    status: str

    def __init__(self, buyer: str, seller: str, terms: str, amount_usdc: int):
        self.buyer = buyer
        self.seller = seller
        self.terms = terms
        self.amount_usdc = amount_usdc
        self.status = "LOCKED"

    @gl.public.write
    def raise_dispute(self) -> str:
        if self.status != "LOCKED":
            return "Error: Already disputed or resolved"
        self.status = "DISPUTED"
        return "Dispute raised"

    @gl.public.view
    def get_status(self) -> str:
        return self.status
