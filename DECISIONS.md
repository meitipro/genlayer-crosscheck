# DECISIONS

What was decided, what was found by running the code, and what is still true
that a reviewer should know.

---

## The design decision everything follows from

**The two `why_` strings are deliberately outside consensus.**

Every other field in a `Check` is agreed by validators. The two explanations are
not, and that is a choice rather than an oversight. Two honest readers describe
the same shortfall differently. "the page never states a fee" and "no fee
appears anywhere in the terms" mean the same thing and share almost no words, so
comparing them would stall every check that was otherwise perfectly agreed.

The cost of that choice is that a leader picks those strings freely. Testing a
deliberately lying leader confirmed it: a leader can leave the verdict and both
framings untouched and still write arbitrary text into the stored record.

That is handled three ways, none of which is "compare the prose":

1. **Sanitised on the way into storage.** Markup, braces, backticks and control
   characters are stripped, whitespace is collapsed, length is capped at 120.
   The strings are stored on chain and rendered by whatever reads them next, so
   they are treated as untrusted text at the boundary.
2. **Nothing acts on them.** No branch in the contract reads a `why_` string.
3. **The view says so.** `latest()` returns
   `reasons_are_leader_supplied: true`, so a consumer cannot mistake them for
   agreed facts.

Covered by `test_a_leader_supplied_reason_is_sanitised_before_storage` and
`test_the_view_says_the_reasons_are_leader_supplied`.


## A read with a negative id returned the newest record

Every view indexed `self.claims[int(claim_id)]` directly. Two failures came out
of one missing line.

An id past the end raised a raw `IndexError`, which GenVM reports as a
**contract error** rather than a user error — a caller learns nothing about
what went wrong.

The worse half: Python list indexing accepts `-1`. A caller asking for claim
`-1` silently received the **newest** claim's verdict, correctly formatted,
with nothing failing anywhere. A consuming contract could act on it and never
know it had read a different claim.

**Fix:** one bounds-checked lookup helper, used by every read.
**Tests:** `test_a_read_with_a_nonexistent_id_is_a_user_error`,
`test_a_read_with_a_negative_id_does_not_return_the_last_record`.

---

## Why the validator has two layers

The obvious design is one layer: re-run the work, compare the verdict. That is
layer 2 and it is necessary. Layer 1 was added because it is free.

```python
# layer 1 — internal honesty, costs nothing
if combine(theirs["positive"], theirs["negative"]) != theirs["verdict"]:
    return False
```

`combine()` is a pure function in the contract, so a validator can check that
the leader's own two answers actually produce the verdict it reported **without
running a single prompt**. A malformed or dishonest proposal is rejected before
any inference is spent on it.

Most validators either trust the leader's structure or re-run everything.
Checking that a proposal is internally consistent sits between the two, costs
nothing, and catches a whole class of failure. It generalises: any contract
whose block returns both inputs and a derived output can verify the derivation
for free.

The same check runs again in the deterministic half, after consensus, before
the verdict is stored — so a stored verdict can never contradict the framings
stored beside it. Covered by
`test_the_verdict_is_recomputed_from_the_stored_framings`.

---

## Why layer 2 compares the verdict and not the framings

Two honest nodes may differ on one framing and still reach the same verdict.
One returns `unclear` on the positive framing and `no` on the negative; another
returns `yes` and `yes`. Both land on `UNSTABLE`, and both are right.

Forcing the raw framings to match would reject correct work and make the
contract fail for reasons unrelated to the claim. Covered by
`test_reaching_unstable_by_different_routes_still_agrees`.

---

## Why the prompts are built from one template

Both framings come from `build_framing()` with a single direction parameter.
This matters more than it looks: if the two prompts differed in tone, length or
specificity, a disagreement between them would be measuring the prompts rather
than the model, and the entire primitive would mean nothing.

A test asserts the two prompts have identical line structure and share every
scaffolding phrase. Covered by `test_the_two_framings_are_symmetric_prompts`.

---

## Why the tests are built the way they are

### The simulator gives each node its own world

[`tests/glsim.py`](tests/glsim.py) runs the non-deterministic block twice — once
as the leader, once as a validator — with **independent** mock pages and prompt
answers:

```python
self.mocks(SUPPORT, v_prompts=REFUTE)   # the validator reached a different verdict
```

A contract that quietly assumes both nodes see identical bytes passes a normal
mocking suite and fails on a real network. Feeding both nodes the same data is
the default in every mocking framework, which is exactly why it is worth
breaking on purpose.

### The unit tests load the real contract source

A contract file cannot simply be imported: it starts with the GenVM dependency
header and does `from genlayer import *`. So `tests/test_logic.py` reads the
real file and executes the helper section with a stub.

The alternative — copying `combine()` into the test file — creates a second copy
that drifts. Here, a change to the contract is a change to what the tests run.

### Mutation testing, because passing tests prove nothing

Every safety property was broken on purpose to confirm a test notices. The table
is in [README.md](README.md#the-tests-have-teeth).

One mutation initially escaped, and it was informative: a defence added later
was strict enough to catch a case an earlier test was supposed to cover, which
left that earlier test unable to fail. It was replaced with one that isolates a
single layer. **A test that cannot fail is worse than no test**, because it
reports coverage it does not provide.

## The storage layout, and why it looks like this

Every collection in this contract is a **top level contract field**. No storage
dataclass contains a `DynArray`, and records carry an id rather than living
inside their parent.

That is not a style preference. It cost two failed deployments.

### What was tried, and what each attempt did

```python
@allow_storage
@dataclass
class Claim:
    checks: DynArray[Check]
```

**Attempt 1** — build it the obvious way:

```python
Claim(..., checks=DynArray[Check]())
# TypeError: this class can't be instantiated by user
```

**Attempt 2** — use the documented escape hatch. The storage page shows
`User(gl.storage.inmem_allocate(TreeMap[str, str]))` working for a nested
`TreeMap`, so the same shape should work for a nested `DynArray`:

```python
Claim(..., checks=gl.storage.inmem_allocate(DynArray[Check]))
# TypeError: _GenericAlias.__init__() missing 1 required positional argument: 'args'
```

It did not. The subscripted generic's `__init__` is not the collection's, so
the allocator calls the wrong one.

**Being precise about this:** the documentation does not say nested collections
are impossible, and `inmem_allocate` is documented as the way to build them. It
failed here for `DynArray[T]` on the deployed runner. Whether that is a version
difference, a difference between `TreeMap` and `DynArray`, or something about
the element type, is not something that could be settled from outside — and a
primitive should not depend on a mechanism that failed once and cannot be tested
locally.

### What the flat shape buys

Top level fields are allocated by the runtime, so nothing has to be constructed
in memory at all. `self.checks` simply exists, zero-initialised to `[]`, and a
`Check` carries the `claim_id` it belongs to.

The cost is a linear walk in the views instead of a direct index. Views are
free to the caller and never run inside a write, so that trade is a bargain for
a shape that cannot fail at deploy time.

### The other rules from the same page, all enforced here

- `list`, `dict` and `int` are **not valid storage types**. Use `DynArray[T]`,
  `TreeMap[K, V]`, and `u256` / `i256` / `bigint`.
- Only **fully instantiated** generics. Bare `TreeMap` is refused.
- Persistent fields must be **declared in the class body** with a type
  annotation. `self.something = value` on an undeclared name is not persistent
  and is silently discarded after execution.
- Storage objects **cannot be used inside a non-deterministic block**. Everything
  the block here closes over is extracted to a plain `str` or list first.
- Calldata mappings support **`str` keys only**, like JSON.
- A storage object is a **view on a slot, not a copy**. Holding a reference
  across a write to that slot gives you the new value, silently. Nothing here
  holds a reference across an append to the same array.

The test suite checks all of this by static analysis, and
[`tests/glsim.py`](tests/glsim.py) refuses at class definition time everything
GenVM refuses at deploy time — so a regression fails on the workstation in
0.2 seconds rather than after a deployment.

---
## A duplicated method shadowed the real one

While flattening the storage, an editing mistake left **two definitions of the
same lookup helper** in the contract. Python allows this silently: the second
definition wins and the first is dead code.

It surfaced through mutation testing. A mutation to the first copy changed
nothing, because the second copy was the one being called, and the mutation was
reported as escaping the tests. The tests were fine; the contract had a hidden
duplicate.

Two static checks now guard it — no method defined twice in a class, no
top-level name defined twice in the module. Both are one assertion each and
both would have caught it immediately.

---

## Honest limits

Things a reviewer should know that the README does not lead with.

### It cannot detect a model that is consistently wrong

This detects framing *sensitivity*. A model that confidently and consistently
misreads the evidence in both directions produces a clean `SUPPORTED` and the
contract has no way to know. It measures self-consistency, not accuracy, and
those are different properties.

Pair it with a corroboration primitive if you need the second one.

### UNSTABLE is not a severity

`UNSTABLE` covers seven different answer combinations, from "the model
contradicted itself" to "the evidence is irrelevant to the claim". They are all
equally unanswerable, but they are not equally interesting, and the contract
does not distinguish them. The stored framings do, for a human reading them.

### One evidence page, frozen

A claim is judged against exactly one url, fixed at registration. That prevents
a caller from picking whichever page supports them today, and it also means a
claim spread across several sources cannot be checked here at all.

### Not upgradable

There is no admin method, no pause, no owner. That is deliberate for a primitive
whose value is that its rules cannot move after somebody depends on them, and it
means a bug found later requires a new deployment.
