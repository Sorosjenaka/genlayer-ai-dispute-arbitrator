# MilestoneEscrowArbiter — AI-Arbitrated Milestone Escrow (GenLayer Intelligent Contract)

Standalone GenLayer Intelligent Contract that escrows freelance / agentic-commerce milestones
and lets GenLayer validator consensus decide whether a deliverable satisfies the agreed terms —
plus a second arbitration pass for disputes.

Live submission target: GenLayer Portal contribution type **52 — Intelligent Contracts**
(`builder`, multiplier 50x at time of writing).

- Contract source: [`contract.py`](./contract.py)
- Raw (for Studio import): `https://raw.githubusercontent.com/Sorosjenaka/genlayer-ai-dispute-arbitrator/main/contract.py`
- Tests: [`test_contract.py`](./test_contract.py) — `python -m pytest test_contract.py -v`

> Deployed (Studionet, demo — no faucet needed):
> - Contract: `0x49a12ACB1601D969B4671BBFccC4c97D8E0D1C81`
> - Explorer: `https://explorer-studio.genlayer.com/address/0x49a12ACB1601D969B4671BBFccC4c97D8E0D1C81`
> - Studio: `https://studio.genlayer.com/?import-contract=0x49a12ACB1601D969B4671BBFccC4c97D8E0D1C81`
> - Deploy tx: `0xb532d83ca3d1ab25aa2c9453db66688b1b5b4a7a818f4cb4f48577498974409f`
>   (status ACCEPTED, consensus MAJORITY_AGREE)
> - Demo escrow #0 on this contract: create `0xf408a850f02e32d7b0754f96b176fc1f35661b6fcd506b35d025957cd94322d7`
>   → fund `0xda300b7959d0232e0221364cab3613d23593eda9b1c30d550ed272d25f3d0a12`
>   → submit `0x32235f99022c9080406181afbfcb31220fade4b55c8165a8356bc5cd2cff4675`
>   → reachable-check `0x73dd667142d2ae4200d077dc7ac537814af4ab8f9ab9badf29d2ff5b15a0824a`
>   → AI verify `0xe8f1a61cefa7fa25f2773306b28277a4f1086f948d37e3d1bfe023cf866a3d30`
>   ⇒ `VERIFIED_APPROVED`, verdict APPROVED, score 96.
>
> For a stronger (testnet) submission, redeploy the same file to Bradbury after
> funding an account via the faucet, then replace the links above.

## Why this is a reusable primitive (not a demo)

Freelance and agent-to-agent deals stall on one question: *"was the work actually done?"*.
This contract answers it on-chain:

1. Buyer creates + funds an escrow with written `terms`.
2. Seller links a `deliverable_url` (deployed site, PR, doc, file).
3. **Any validator set** fetches the URL and judges it against the terms via LLM consensus.
4. If disputed, a **separate arbitration** weighs terms + deliverable + dispute reason and
   rules `RELEASE_SELLER | REFUND_BUYER | SPLIT`.
5. Settlement (`release` / `refund`) is deterministic and only allowed from the correct
   consensus state.

## How consensus is used (for reviewers)

| Method | Pattern | Decision fields compared | Ignored (by design) |
|---|---|---|---|
| `verify_deliverable` | `gl.vm.run_nondet_unsafe`, leader + validator both `web.get` + `exec_prompt` | `verdict` exact match; `score` within ±15 | `reasoning` text (subjective wording differs per LLM) |
| `arbitrate_dispute` | `gl.vm.run_nondet_unsafe`, re-fetches deliverable + dispute evidence | `ruling` exact match; `confidence` within ±20; SPLIT gated | `reasoning` text |
| `check_deliverable_reachable` | `gl.eq_principle.strict_eq` | canonicalized `{"reachable": bool}` exact | — (deterministic bool, so strict_eq is correct) |

Validators never trust the leader: they re-run the fetch + prompt independently.
Leader errors (`UserError` / non-`Return`) are rejected. Storage is copied to memory
(`gl.storage.copy_to_memory`) before nondet blocks; all state writes happen after consensus.

## State design

```python
escrows: TreeMap[str, Escrow]   # deal records by string id
escrow_ids: DynArray[str]       # insertion-order index
next_id: u256                   # monotonic counter
owner: str                      # deployer hex
```

`Escrow` (`@allow_storage` dataclass): buyer, seller, terms, amount (`u256`),
deliverable_url/note, status, verdict, score (`u256`), reasoning,
dispute_reason, dispute_evidence_url, ruling, confidence (`u256`).

Statuses: `CREATED → FUNDED → SUBMITTED → VERIFIED_APPROVED | VERIFIED_REVISION | VERIFIED_REJECTED → DISPUTED → RESOLVED_SELLER | RESOLVED_BUYER | RESOLVED_SPLIT`.

## Methods

Write: `create_escrow | fund_escrow | submit_deliverable | check_deliverable_reachable |
verify_deliverable | raise_dispute | arbitrate_dispute | release | refund`

View: `get_escrow | list_escrows | get_stats`

## Deploy (Bradbury testnet)

Network: `testnet-bradbury` — chain `4221`, RPC `https://rpc-bradbury.genlayer.com`,
explorer `https://explorer-bradbury.genlayer.com/`.

```bash
# 1. account (once)
genlayer account create --name soros
genlayer account use soros
genlayer network set testnet-bradbury

# 2. faucet: https://testnet-faucet.genlayer.foundation/ -> paste your address
genlayer account show

# 3. deploy (no constructor args)
genlayer deploy --contract ./contract.py

# 4. note the contract address, then open:
# explorer: https://explorer-bradbury.genlayer.com/address/0xYOUR_CONTRACT
# studio:   https://studio.genlayer.com/?import-contract=0xYOUR_CONTRACT
```

Studio alternative: open Studio → Import contract → paste raw GitHub URL or contract
address → constructor takes no args → deploy from Studio UI.

## End-to-end demo (CLI)

```bash
ADDR=0xYOUR_CONTRACT
SELLER=0xSellerAddressHere

# buyer creates + funds
genlayer write $ADDR create_escrow --args $SELLER "Build landing page with hero, pricing, contact form. Must be deployed." 1000
genlayer write $ADDR fund_escrow --args 0

# seller submits (switch account to seller first: genlayer account use seller)
genlayer write $ADDR submit_deliverable --args 0 https://example.com/deliverable "Deployed site, see URL"

# anyone verifies (AI consensus)
genlayer write $ADDR verify_deliverable --args 0
genlayer call $ADDR get_escrow --args 0

# optional dispute + arbitration
genlayer write $ADDR raise_dispute --args 0 "Contact form missing validation" ""
genlayer write $ADDR arbitrate_dispute --args 0

# settlement (buyer)
genlayer write $ADDR release --args 0
# or: genlayer write $ADDR refund --args 0
```

## Tests

```bash
python -m pytest test_contract.py -v
# 7 passed: happy path, validation, auth guards, rejected->refund, dispute->arbitrate, views
```

Tests mock the `genlayer` SDK (no node needed) and cover deterministic logic.
On-chain consensus paths should additionally be exercised once in Studio/testnet
(`verify_deliverable` + `arbitrate_dispute` on a real URL) before submitting —
quote the resulting tx hashes in the portal notes.

## Portal submission (type 52) — copy/paste template

Evidence group required: **(GitHub repo OR Studio link) + (Explorer contract link)**.
Attach at least:

1. `https://github.com/Sorosjenaka/genlayer-ai-dispute-arbitrator`
2. `https://explorer-bradbury.genlayer.com/address/0xYOUR_CONTRACT`
3. optional but recommended: `https://studio.genlayer.com/?import-contract=0xYOUR_CONTRACT`

See [`SUBMISSION.md`](./SUBMISSION.md) for the full title/description/notes text.

## License

MIT
