# Crosscheck — specification

Purpose, consensus, state, API, reuse. Written so a reviewer can judge the
design without opening the source, and so a builder can decide whether to lift
it without reading the tests.

---

**File:** [`contracts/crosscheck.py`](contracts/crosscheck.py) · 49 tests
**Runner:** `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`

### Purpose

Answer a yes/no question about evidence, and refuse when the answer would depend
on how the question was worded.

A model asked "does this evidence support the claim?" and the same model asked
"does this evidence contradict the claim?" should give mirrored answers. Often it
does not. Ask positively and it agrees; ask negatively and it agrees again.

Validator consensus does not catch this. Every validator runs the same single
framing, every validator gets the same flattering answer, and the network
confidently agrees on a result that would have flipped under the other wording.
Framing sensitivity is invisible to a mechanism that only checks whether nodes
match each other.

### Consensus

`gl.vm.run_nondet_unsafe`. Two prompts run **sequentially in one block** —
sequential prompts are legal, nested non-deterministic blocks are not. The block
returns the positive answer, the negative answer, and the verdict combining them.

The combination rule is pure and total:

```python
if p == YES and n == NO:   return SUPPORTED
if p == NO  and n == YES:  return REFUTED
return UNSTABLE            # the model told two stories
```

Only two of nine combinations are internally consistent. Double-yes ("it both
supports and contradicts") and double-no ("it neither supports nor contradicts")
both collapse to `UNSTABLE`, as does any `unclear`.

The validator has **two independent layers**:

```python
# layer 1 — internal honesty, costs nothing
#   combine() is pure, so the validator checks the leader's own arithmetic
#   without running a prompt. a leader reporting SUPPORTED while its own two
#   answers say otherwise is caught at zero inference cost.
if combine(theirs["positive"], theirs["negative"]) != theirs["verdict"]:
    return False

# layer 2 — agreement on the verdict, never on the raw framings
#   two honest nodes may differ on one framing and still land on the same
#   verdict. forcing the framings to match would reject correct work.
return mine["verdict"] == theirs["verdict"]
```

Layer 1 is the part worth stealing. Most validators either trust the leader's
structure or re-run everything. Checking that the leader's output is internally
consistent is free, deterministic, and catches a whole class of malformed or
dishonest proposals before any model is invoked.

Both prompts are built from **one symmetrical template** differing only in
direction. If the two framings differed in tone, length or specificity, a
disagreement between them would measure the prompts rather than the model, and
the primitive would mean nothing. A test asserts they have identical structure.

### State

| Field | Shape | Note |
|---|---|---|
| `claims` | `DynArray[Claim]` | append-only |
| `Claim.text` | `str` | 12–300 chars; a fragment is not a claim, and 300+ is several |
| `Claim.evidence_url` | `str` | **frozen at registration** |
| `Claim.checks` | `DynArray[Check]` | full history, never overwritten |
| `Claim.n_supported / n_refuted / n_unstable` | `u256` | counters for `stability()` |

The evidence url is frozen with the claim on purpose. Letting a caller supply
evidence at check time would let them pick whichever page supports them today.

The two `why_` strings inside a `Check` are **leader-supplied and deliberately
outside consensus**: two honest readers describe the same shortfall differently,
and comparing prose would stall every check. Because a leader picks them freely,
they are sanitised on the way *into* storage — markup, braces, backticks and
control characters stripped, length capped — and `latest()` returns
`reasons_are_leader_supplied: true` so no consumer mistakes them for facts.

### API

```python
register(text: str, evidence_url: str)   # freeze a claim and its evidence
check(claim_id: u256)                    # two framings, one block, one verdict

verdict(claim_id)   -> str    # supported | refuted | unstable | unreadable
latest(claim_id)    -> dict   # the verdict, both framings, and the honesty flag
stability(claim_id) -> dict   # {checks, supported, refuted, unstable, unstable_pct}
count()             -> u256
```

`check()` may be called by anyone. The caller cannot influence what is read or
how it is judged.

### Reuse

A confidence gate in front of anything that acts on an LLM judgment. Fact
checking, dispute triage, claim verification, moderation appeals, release gating.

`UNSTABLE` is the load-bearing result. Contracts needing certainty should treat
it as "do nothing", which is almost always correct and almost never what a
single-framing contract would have done.

`stability()` turns the primitive into a measuring instrument for the claim
itself: a high unstable rate says the claim is worded so a reasonable reader
could go either way, which is worth knowing before acting on it.
