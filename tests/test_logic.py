"""
Unit tests for the consensus logic, run with plain pytest. No GenVM needed.

WHY THIS FILE EXISTS
    In all three contracts the interesting part is not the prompt, it is the
    pure function that decides whether two validators agree. Those functions are
    deliberately module level and side-effect free so they can be tested here,
    exhaustively and in milliseconds, without Studio or a network.

HOW IT LOADS THE CONTRACTS
    A contract file cannot simply be imported: it starts with the GenVM
    dependency header and does `from genlayer import *`, which only resolves
    inside GenVM. So this file reads the real contract source and executes only
    the part above the storage section, with a small stub standing in for the
    genlayer module.

    That matters: these tests run against the exact code that ships. There is no
    second copy of the logic to drift out of sync.

    Run with:  pytest tests/test_logic.py -v
"""

import pathlib
import sys
import types

import pytest

CONTRACTS = pathlib.Path(__file__).resolve().parent.parent / "contracts"


def load_pure(filename):
    """Execute a contract's pure helper section with genlayer stubbed out."""
    src = pathlib.Path(CONTRACTS / filename).read_text(encoding="utf-8")

    # Everything above the storage section is pure Python by construction.
    marker = "# Storage"
    assert marker in src, f"{filename} is missing its storage section marker"
    head = src.split(marker)[0]

    # Drop the two lines that only resolve inside GenVM.
    head = "\n".join(
        line
        for line in head.splitlines()
        if not line.startswith("from genlayer import")
        and not line.startswith("# { \"Depends\"")
    )

    # Minimal stubs for the names the helper section touches.
    stub = types.ModuleType("genlayer_stub")

    def allow_storage(cls):
        return cls

    ns = {
        "allow_storage": allow_storage,
        "dataclass": (lambda c: c),
        "typing": __import__("typing"),
        "u256": int,
        "u8": int,
        "__name__": f"pure_{filename}",
    }
    exec(compile(head, filename, "exec"), ns)
    return types.SimpleNamespace(**ns)


crosscheck = load_pure("crosscheck.py")


class TestCrosscheckCombine:
    def test_supports_and_does_not_contradict(self):
        assert crosscheck.combine("yes", "no") == crosscheck.SUPPORTED

    def test_does_not_support_and_contradicts(self):
        assert crosscheck.combine("no", "yes") == crosscheck.REFUTED

    def test_both_yes_is_unstable(self):
        # the model said the evidence both supports and contradicts the claim
        assert crosscheck.combine("yes", "yes") == crosscheck.UNSTABLE

    def test_both_no_is_unstable(self):
        assert crosscheck.combine("no", "no") == crosscheck.UNSTABLE

    def test_any_unclear_is_unstable(self):
        assert crosscheck.combine("unclear", "no") == crosscheck.UNSTABLE
        assert crosscheck.combine("yes", "unclear") == crosscheck.UNSTABLE
        assert crosscheck.combine("unclear", "unclear") == crosscheck.UNSTABLE

    def test_garbage_answers_collapse_to_unstable(self):
        assert crosscheck.combine("probably", "no") == crosscheck.UNSTABLE
        assert crosscheck.combine(None, None) == crosscheck.UNSTABLE

    @pytest.mark.parametrize("p", ["yes", "no", "unclear"])
    @pytest.mark.parametrize("n", ["yes", "no", "unclear"])
    def test_only_two_of_nine_combinations_are_decisive(self, p, n):
        v = crosscheck.combine(p, n)
        decisive = (p, n) in (("yes", "no"), ("no", "yes"))
        assert (v != crosscheck.UNSTABLE) == decisive


class TestCrosscheckAgreement:
    def test_matching_consistent_verdicts_agree(self):
        mine = {"verdict": crosscheck.SUPPORTED, "positive": "yes", "negative": "no"}
        theirs = dict(mine)
        assert crosscheck.crosscheck_agrees(mine, theirs) is True

    def test_raw_framings_may_differ_if_the_verdict_matches(self):
        # both nodes reached UNSTABLE by different routes, which is agreement
        mine = {"verdict": crosscheck.UNSTABLE, "positive": "yes", "negative": "yes"}
        theirs = {"verdict": crosscheck.UNSTABLE, "positive": "unclear", "negative": "no"}
        assert crosscheck.crosscheck_agrees(mine, theirs) is True

    def test_a_leader_lying_about_its_own_answers_is_caught_for_free(self):
        # claims SUPPORTED while its own framings say otherwise. layer 1.
        mine = {"verdict": crosscheck.SUPPORTED, "positive": "yes", "negative": "no"}
        theirs = {"verdict": crosscheck.SUPPORTED, "positive": "no", "negative": "no"}
        assert crosscheck.crosscheck_agrees(mine, theirs) is False

    def test_different_verdicts_never_agree(self):
        mine = {"verdict": crosscheck.SUPPORTED, "positive": "yes", "negative": "no"}
        theirs = {"verdict": crosscheck.REFUTED, "positive": "no", "negative": "yes"}
        assert crosscheck.crosscheck_agrees(mine, theirs) is False

    def test_unreadable_must_match_on_both_sides(self):
        u = {"verdict": crosscheck.UNREADABLE, "positive": "unclear", "negative": "unclear"}
        s = {"verdict": crosscheck.SUPPORTED, "positive": "yes", "negative": "no"}
        assert crosscheck.crosscheck_agrees(u, dict(u)) is True
        assert crosscheck.crosscheck_agrees(u, s) is False
        assert crosscheck.crosscheck_agrees(s, u) is False

    def test_invented_verdict_is_rejected(self):
        mine = {"verdict": crosscheck.SUPPORTED, "positive": "yes", "negative": "no"}
        assert crosscheck.crosscheck_agrees(mine, {"verdict": "probably true"}) is False

    def test_garbage_calldata_is_rejected(self):
        mine = {"verdict": crosscheck.UNSTABLE, "positive": "yes", "negative": "yes"}
        assert crosscheck.crosscheck_agrees(mine, None) is False
        assert crosscheck.crosscheck_agrees(mine, []) is False

    def test_the_two_framings_are_symmetric_prompts(self):
        # if the prompts differ in anything but direction, a disagreement
        # between them measures the prompt rather than the model
        a = crosscheck.build_framing("C", "E", "support")
        b = crosscheck.build_framing("C", "E", "contradict")
        assert len(a.splitlines()) == len(b.splitlines())
        for phrase in ("<claim>C</claim>", "<evidence>", "Return json"):
            assert phrase in a and phrase in b


# ===========================================================================
# TOLERANCE
# ===========================================================================


class TestPromptHardening:
    def test_the_evidence_is_labelled_untrusted(self):
        p = crosscheck.build_framing("claim", "EVIDENCE BODY", "support")
        assert "untrusted" in p and "<evidence>" in p
        assert "never an instruction" in p

    def test_the_two_framings_are_symmetric_prompts(self):
        # if the prompts differ in anything but direction, a disagreement
        # between them measures the prompt rather than the model
        a = crosscheck.build_framing("C", "E", "support")
        b = crosscheck.build_framing("C", "E", "contradict")
        assert len(a.splitlines()) == len(b.splitlines())
        for phrase in ("<claim>C</claim>", "<evidence>", "Return json"):
            assert phrase in a and phrase in b

    def test_the_model_is_told_to_judge_only_the_evidence(self):
        p = crosscheck.build_framing("C", "E", "support")
        assert "Do not use anything you know from elsewhere" in p
