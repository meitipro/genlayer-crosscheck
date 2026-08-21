# Crosscheck — a framing-sensitivity detector for LLM-backed contracts

A reusable primitive that answers a yes/no question about evidence by asking it **twice in opposite framings** inside a single non-deterministic block, and refusing to answer when the two framings disagree with each other.

- **Contract:** [`contracts/crosscheck.py`](contracts/crosscheck.py)
- **Tests:** `pytest tests/ -q` → **49 passed**, nothing to install but pytest
- **Deployed:** `{address}` ([explorer](https://explorer-studio.genlayer.com/address/{address}))
- **Specification:** [CONTRACTS.md](CONTRACTS.md)
- **Decisions and limits:** [DECISIONS.md](DECISIONS.md)
- **License:** MIT. Copy the agreement rule; that is what it is for.

---

## The problem

A model asked "does this evidence support the claim?" and the same model
asked "does this evidence contradict the claim?" should give mirrored
answers. Often it does not. Ask it positively and it agrees; ask it
negatively and it agrees again.

**Validator consensus does not catch this.** Every validator runs the same
single framing, every validator gets the same flattering answer, and the
network confidently agrees on a result that would have flipped if the
question had been worded the other way.

## How consensus is used

Two prompts run sequentially in **one** block. Sequential prompts are legal;
nested non-deterministic blocks are not. The block returns the positive
answer, the negative answer, and the verdict combining them.

Only two of the nine combinations are internally consistent:

```python
if p == YES and n == NO:   return SUPPORTED
if p == NO  and n == YES:  return REFUTED
return UNSTABLE            # the model told two stories
```

The validator rule has two independent layers:

```python
# layer 1 — internal honesty, costs nothing
#   combine() is pure, so the validator checks the leader's own arithmetic
#   without running a single prompt. a leader reporting SUPPORTED while its
#   own two answers say otherwise is caught at zero inference cost.
if combine(theirs["positive"], theirs["negative"]) != theirs["verdict"]:
    return False

# layer 2 — agreement on the verdict, not on the raw framings
#   two honest nodes may differ on one framing and still land on the same
#   verdict. forcing the framings to match would reject correct work.
return mine["verdict"] == theirs["verdict"]
```

Layer 1 is the part worth stealing. Most validators either trust the
leader's structure or re-run everything; checking that the leader's output is
internally consistent is free, deterministic, and catches a whole class of
malformed proposals before any model is invoked.

## Why this is not a thin LLM wrapper

The model produces two yes/no/unclear answers. It never produces the verdict.
The verdict comes from a pure combination function in the deterministic half,
and is recomputed from the stored framings before being written, so a stored
verdict can never contradict the record beneath it.

The primitive also measures the model rather than trusting it: `stability()`
publishes how often a claim comes back unstable.

### The reasons are not consensus, and say so

The two `why_` strings are chosen by the leader and deliberately excluded
from consensus: two honest readers describe the same shortfall differently,
and comparing prose would stall every check. That means a leader picks them
freely, so they are treated as untrusted text on the way **into** storage —
markup, braces, backticks and control characters are stripped and the length
is capped. Nothing in the contract acts on them, and `latest()` returns
`reasons_are_leader_supplied: true` so no consumer mistakes them for facts.

---

## The API

```python
register(text, evidence_url)   # freeze the claim and its evidence
check(claim_id)                # two framings, one block, one verdict

verdict(claim_id)   -> str    # supported | refuted | unstable | unreadable
latest(claim_id)    -> dict   # the verdict and both framings behind it
stability(claim_id) -> dict   # how often this claim is unanswerable
count()             -> int
```

The evidence url is frozen with the claim. Letting a caller supply evidence
at check time would let them pick whichever page supports them today.

## Using it from another contract

```python
@gl.contract_interface
class Crosscheck:
    class View:
        def verdict(self, claim_id: int) -> str: ...



# in a consuming contract: act only on a stable verdict
v = Crosscheck(CROSSCHECK_ADDR).view().verdict(cid)
if v == "supported":
    self._proceed()
# unstable and unreadable both mean: do nothing
```

`UNSTABLE` is not a consensus failure. The network agrees, precisely, that
this claim cannot be answered reliably against this evidence right now.
Contracts needing certainty should treat it as "do nothing", which is almost
always correct and almost never what a single-framing contract would do.

---

## Running the tests

```bash
pip install pytest
pytest tests/ -q
```

```
49 passed, 1 skipped
```

Three suites, covering different things.

**`tests/test_logic.py`** — the pure agreement rules, exhaustively. They are
module-level functions in the contract, so this file reads the **real contract
source** and executes the helper section with a stub for `genlayer`. There is no
second copy of the logic to drift out of sync.

**`tests/test_e2e.py`** — the contract itself, executed. It runs on
[`tests/glsim.py`](tests/glsim.py), a small GenVM stand-in included here, so it
needs no Studio and no network. This is what reaches the deterministic half:
storage round-trips, the post-consensus re-derivation, and every branch that
only fires when the leader and a validator see different things.

The important part is that the leader and the validator get **their own** mock
pages and prompt answers, so a contract that quietly assumes both nodes see
identical bytes fails here rather than on a real network.

**`tests/test_integration.py`** — against a real Studio, skipped automatically
when `genlayer-test` is not installed:

```bash
pip install genlayer-test
gltest --network studionet tests/test_integration.py
```

### The tests have teeth

Passing tests prove nothing on their own, so every safety property was broken on
purpose to confirm a test notices. Across the three primitives in this family,
seventeen mutations were introduced and all seventeen were caught. The ones
covering this contract:

| Mutation | Caught by |
|---|---|
| the internal-honesty layer removed | `test_a_leader_lying_about_its_own_answers_is_caught_for_free` |
| double-yes treated as supported | `test_a_model_that_agrees_with_both_framings_is_caught` |
| the verdict trusted instead of recomputed before storing | `test_the_verdict_is_recomputed_from_the_stored_framings` |
| the reason sanitiser disabled | `test_markup_is_stripped` |
| control characters left in stored reasons | `test_control_characters_become_spaces` |

---

## Deploying

```bash
npm i -g genlayer
./scripts/deploy.sh studionet
```

`deploy.sh` lints, deploys, and then **exercises** the contract, so the explorer
page shows real method calls with consensus results rather than only a deploy.

---

## Design rules

- **Nothing outside the closed set gets through.** Every model output is mapped
  onto a declared vocabulary, band, or number, and re-checked in Python *after*
  the block returns.
- **The deterministic half re-derives, it does not trust.** The verdict is recomputed from the block's own two
  answers before storage, so the stored verdict always follows from the
  stored framings.
- **Untrusted input is labelled as such.** The prompt is built in contract code;
  no caller string reaches the instruction part. Evidence sits inside tags and is
  named as data that is never an instruction, and text addressing the model is
  itself grounds for refusing to answer.
- **Refusing is a designed outcome.** `unstable` and `unreadable` are both first-class results. A primitive that must always
  produce an answer will produce a wrong one.
- **Frozen at registration.** The claim text and the evidence url. If these could be chosen later, whoever
  triggered the call would be choosing what the network reads.

## Further reading in this repository

- [CONTRACTS.md](CONTRACTS.md) — the full specification: purpose, consensus,
  state model, API, reuse
- [DECISIONS.md](DECISIONS.md) — engineering decisions, what testing found, and
  the honest limits
- [lib/crosscheck_consensus.py](lib/crosscheck_consensus.py) — the agreement rules on
  their own, to be copied

## Related work

A separate primitive, built to the same standard and submitted independently:
[Tolerance](https://github.com/meitipro/genlayer-tolerance) — per-field numeric agreement and plausibility guards.

The two share an author and a discipline, not a codebase. Each deploys, tests
and is used entirely on its own.

---

Published by [InferNode](https://x.com/Infer_node).
