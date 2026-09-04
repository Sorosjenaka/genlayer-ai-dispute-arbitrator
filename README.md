# GenLayer AI Dispute Arbitrator & Escrow

Decentralized escrow and dispute resolution smart contract built for GenLayer.

## Overview

This project implements an AI-powered dispute resolution system for escrow contracts on GenLayer. It leverages GenLayer's Intelligent Contracts with AI consensus to adjudicate disputes between buyers and sellers without requiring centralized intermediaries.

## Features

- **Escrow Management**: Lock funds until terms are met
- **Evidence Submission**: Both parties can submit evidence
- **AI Arbitration**: GenLayer AI consensus determines the winner
- **Automatic Fund Distribution**: Based on arbiter ruling

## Contract States

1. `LOCKED` - Initial state, funds locked in escrow
2. `DISPUTED` - Dispute raised, awaiting AI arbitration
3. `RESOLVED_BUYER` - Funds released to buyer
4. `RESOLVED_SELLER` - Funds released to seller
5. `RESOLVED_SPLIT` - Funds split between parties

## Usage

```python
from genlayer import Contract, gl

class DisputeEscrowContract(Contract):
    def __init__(self, buyer: str, seller: str, terms: str, amount_usdc: int):
        # Initialize escrow with buyer, seller, terms, and amount
        pass
    
    @gl.public
    def deposit_funds(self):
        # Deposit funds into escrow
        pass
    
    @gl.public
    def submit_evidence(self, party: str, text_evidence: str):
        # Submit evidence for dispute
        pass
    
    @gl.public
    def raise_dispute(self):
        # Raise a dispute to start AI arbitration
        pass
    
    @gl.public
    def execute_ai_arbitration(self):
        # Execute AI arbitration to resolve dispute
        pass
    
    @gl.public
    def release_funds(self):
        # Release funds based on current state
        pass
```

## Running Tests

```bash
python -m pytest test_contract.py -v
```

## License

MIT
