# Portal submission text — contribution type 52 (Intelligent Contracts)

## Title
MilestoneEscrowArbiter — AI-Arbitrated Milestone Escrow (dual-consensus Intelligent Contract)

## Description / Notes (paste into portal)
Standalone GenLayer Intelligent Contract for freelance/agentic-commerce milestone escrow
with TWO independent AI consensus passes.

What it does:
- Buyer creates + funds escrow with written terms; seller submits a deliverable URL.
- verify_deliverable: every validator independently fetches the deliverable URL
  (gl.nondet.web.get) and judges it vs terms (gl.nondet.exec_prompt) -> {verdict, score 0-100, reasoning}.
  Stored to state; drives VERIFIED_APPROVED / NEEDS_REVISION / VERIFIED_REJECTED.
- arbitrate_dispute: separate pass over terms + deliverable + dispute reason/evidence
  -> {ruling RELEASE_SELLER|REFUND_BUYER|SPLIT, confidence, reasoning} -> resolved status.
- Deterministic settlement (release/refund) only from the correct consensus state.
- check_deliverable_reachable uses strict_eq for the deterministic URL-reachable bool.

How consensus is used (verifier detail):
- Both AI methods use gl.vm.run_nondet_unsafe with full leader/validator re-execution.
  Validators re-run web fetch + prompt; accept only on exact verdict/ruling match plus
  score tolerance ±15 / confidence ±20. Reasoning text is stored but never compared
  (LLM wording differs; comparing it would break consensus without security gain).
  Leader UserError/non-Return is rejected. Storage copied via gl.storage.copy_to_memory
  before nondet blocks; writes happen after consensus.
- strict_eq is used ONLY where the answer is deterministic (reachable bool),
  canonicalized via json sort_keys.

State: TreeMap[str, Escrow] + DynArray[str] index + u256 counter + owner; Escrow is an
@allow_storage dataclass (buyer/seller/terms/amount/deliverable/status/verdict/score/
reasoning/dispute/ruling/confidence).

Quality: readable source with consensus rationale comments, 7 offline unit tests
(pass), README with deploy + end-to-end CLI demo. Tested on Bradbury testnet +
Studio (see tx/contract links in evidence).

## Evidence URLs (attach all three)
1. GitHub repo: https://github.com/Sorosjenaka/genlayer-ai-dispute-arbitrator
2. Explorer contract: https://explorer-bradbury.genlayer.com/address/0xYOUR_CONTRACT
   (replace after deploy; include one verify_deliverable tx hash in notes)
3. Studio contract: https://studio.genlayer.com/?import-contract=0xYOUR_CONTRACT

## Pre-submit checklist
- [ ] Deployed to Bradbury (genlayer deploy --contract ./contract.py), address noted
- [ ] Called on testnet at least: create_escrow, fund_escrow, submit_deliverable (real URL), verify_deliverable
- [ ] Explorer link opens the contract; Studio import link works
- [ ] README raw link works; tests pass (python -m pytest test_contract.py -v)
- [ ] Max 2 submissions/week for type 52 — make this one count
