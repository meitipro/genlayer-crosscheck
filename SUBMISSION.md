# Submission

One submission, under **Builder -> Intelligent Contracts**. This repository is
one standalone primitive. It is not part of a larger project and does not depend
on anything else.

---

## Before you submit, in order

1. **Deploy and exercise.** `./scripts/deploy.sh studionet`. It deploys the
   contract and then calls its methods, so the explorer page shows real
   transactions with consensus results rather than only a deploy.

2. **Open the explorer page and check it.** It must show a Deploy transaction
   **and** at least one method call with a Consensus Result beside it. A page
   with only a deploy proves the file compiles and nothing else. This is the
   strongest single artifact in the submission.

3. **Paste the address** into README.md and into this file wherever the
   placeholder appears, then push.

4. **Submit** with the title, notes and links below.

---

## Title

```
Crosscheck: a framing-sensitivity detector for LLM-backed contracts
```

## Notes (989 characters, the box caps at 1000)

```
Crosscheck is a reusable framing-sensitivity detector for LLM-backed contracts. Ask a model whether evidence SUPPORTS a claim and it agrees; ask whether it CONTRADICTS the same claim and it often agrees again. Consensus misses this: every validator runs the same single framing, so the network agrees on an answer that would have flipped had the question been worded the other way. The contract uses gl.vm.run_nondet_unsafe and runs BOTH framings in one block. Only yes/no and no/yes are internally consistent; the other seven combinations become UNSTABLE. The validator has two layers. Layer one is a free internal honesty check: combine() is pure, so a validator confirms the leader's own two answers produce the verdict it reported, before running any prompt. Layer two compares ONLY the verdict, never the raw framings, since two honest nodes may differ on one framing and still agree. Reusable as a confidence gate. Deployed at {address} on studionet.
```

## Links

```
GitHub:   https://github.com/YOUR_HANDLE/genlayer-crosscheck
Contract: https://github.com/YOUR_HANDLE/genlayer-crosscheck/blob/main/contracts/crosscheck.py
Explorer: https://explorer-studio.genlayer.com/address/{address}
```

---

## What clears the bar, line by line

The category rejects "thin LLM wrappers" and "generic AI decides X demos".

- **The model never decides.** It produces two yes/no/unclear answers. The verdict comes from a pure
  combination function and is recomputed from the stored answers before storage.
- **The validator function is the contribution.** This contract exists to
  demonstrate one agreement rule, explained in [CONTRACTS.md](CONTRACTS.md)
  with the code beside it.
- **Refusing is designed.** UNSTABLE and UNREADABLE are first-class results, not errors.
- **The tests have teeth.** 49 passing is a claim; the mutation table in
  [README.md](README.md#the-tests-have-teeth) is evidence.
- **It runs with nothing installed.** `pip install pytest && pytest tests/ -q`.
  A reviewer with two minutes can verify the whole thing.
- **The limits are stated.** [DECISIONS.md](DECISIONS.md) says what this cannot
  do, including the case it structurally cannot detect.
