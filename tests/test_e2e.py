"""
End-to-end tests. The real contract files, executed.

tests/test_logic.py covers the pure agreement rules. This file covers everything
they cannot reach: the deterministic half of each method, storage round-trips,
the re-derivation checks, the plausibility gate, and the branches that only fire
when the leader and a validator see different things.

It runs on tests/glsim.py, a small GenVM stand-in, so it needs no Studio and no
network:

    pytest tests/test_e2e.py -v

The important trick is set_mocks(): the leader and the validator get their own
web pages and their own prompt answers. Any contract that quietly assumes both
nodes see identical bytes fails here rather than on a real network.
"""

import pytest

import glsim as S


PAGE = (
    "Status page. The mainnet contracts are verified on the explorer. "
    "Withdrawal fee is 0.4 percent. Visitors today: 1,204. "
    "Treasury balance: 50,000 GEN."
) * 3

BLANK = "   "
DOWN = S.UserError("connection refused")


SUPPORT = {
    "Does the evidence SUPPORT": {"answer": "yes", "because": "fee is 0.4 percent"},
    "Does the evidence CONTRADICT": {"answer": "no", "because": "nothing contradicts"},
}
REFUTE = {
    "Does the evidence SUPPORT": {"answer": "no", "because": "fee is 4 percent"},
    "Does the evidence CONTRADICT": {"answer": "yes", "because": "page says 4"},
}
BOTH_YES = {
    "Does the evidence SUPPORT": {"answer": "yes", "because": "seems so"},
    "Does the evidence CONTRADICT": {"answer": "yes", "because": "also seems so"},
}
BOTH_NO = {
    "Does the evidence SUPPORT": {"answer": "no", "because": "unrelated"},
    "Does the evidence CONTRADICT": {"answer": "no", "because": "unrelated"},
}

CLAIM = "The withdrawal fee is under one percent."

class TestCrosscheck:
    def deploy(self, claim=CLAIM):
        c = S.deploy("contracts/crosscheck.py")
        S.call(c, "register", claim, "https://a.example/terms")
        return c

    def mocks(self, prompts, v_prompts=None, page=PAGE, v_page=None):
        S.set_mocks(
            leader_pages={"a.example": page},
            leader_prompts=prompts,
            validator_pages={"a.example": v_page if v_page is not None else page},
            validator_prompts=v_prompts if v_prompts is not None else prompts,
        )

    # -- the three verdicts ------------------------------------------------

    def test_mirrored_answers_support(self):
        c = self.deploy()
        self.mocks(SUPPORT)
        S.call(c, "check", 0)
        assert c.verdict(0) == "supported"
        assert c.latest(0)["framings"] == {
            "supports": "yes", "contradicts": "no",
            "why_supports": "fee is 0.4 percent",
            "why_contradicts": "nothing contradicts",
        }

    def test_mirrored_the_other_way_refutes(self):
        c = self.deploy()
        self.mocks(REFUTE)
        S.call(c, "check", 0)
        assert c.verdict(0) == "refuted"

    def test_a_model_that_agrees_with_both_framings_is_caught(self):
        """The failure this primitive exists for. A single-framing contract
        would have recorded 'supported' and never known."""
        c = self.deploy()
        self.mocks(BOTH_YES)
        S.call(c, "check", 0)
        assert c.verdict(0) == "unstable"

    def test_a_model_that_denies_both_framings_is_also_unstable(self):
        c = self.deploy()
        self.mocks(BOTH_NO)
        S.call(c, "check", 0)
        assert c.verdict(0) == "unstable"

    def test_garbage_answers_collapse_to_unstable(self):
        c = self.deploy()
        self.mocks({
            "Does the evidence SUPPORT": {"answer": "probably", "because": "x"},
            "Does the evidence CONTRADICT": {"answer": 42, "because": "y"},
        })
        S.call(c, "check", 0)
        assert c.verdict(0) == "unstable"

    # -- unreadable evidence -----------------------------------------------

    def test_a_blank_page_is_its_own_verdict(self):
        c = self.deploy()
        self.mocks(SUPPORT, page=BLANK)
        S.call(c, "check", 0)
        assert c.verdict(0) == "unreadable"

    def test_an_unreachable_page_is_its_own_verdict(self):
        c = self.deploy()
        self.mocks(SUPPORT, page=DOWN)
        S.call(c, "check", 0)
        assert c.verdict(0) == "unreadable"

    def test_an_unreadable_verdict_is_not_counted_as_instability(self):
        c = self.deploy()
        self.mocks(SUPPORT, page=DOWN)
        S.call(c, "check", 0)
        s = c.stability(0)
        assert s["checks"] == 0 and s["unstable"] == 0

    # -- consensus ---------------------------------------------------------

    def test_nodes_reaching_different_verdicts_do_not_agree(self):
        c = self.deploy()
        self.mocks(SUPPORT, v_prompts=REFUTE)
        with pytest.raises(S.UserError):
            S.call(c, "check", 0)
        assert c.latest(0)["checked"] is False

    def test_reaching_unstable_by_different_routes_still_agrees(self):
        """Two honest nodes may differ on one framing and still land on the
        same verdict. Forcing the framings to match would reject correct work."""
        c = self.deploy()
        other_route = {
            "Does the evidence SUPPORT": {"answer": "unclear", "because": "a"},
            "Does the evidence CONTRADICT": {"answer": "no", "because": "b"},
        }
        self.mocks(BOTH_YES, v_prompts=other_route)
        S.call(c, "check", 0)
        assert c.verdict(0) == "unstable"

    def test_one_node_reading_a_page_the_other_cannot_is_a_disagreement(self):
        c = self.deploy()
        self.mocks(SUPPORT, page=PAGE, v_page=BLANK)
        with pytest.raises(S.UserError):
            S.call(c, "check", 0)

    def test_both_nodes_finding_it_unreadable_agree(self):
        c = self.deploy()
        self.mocks(SUPPORT, page=BLANK, v_page=BLANK)
        S.call(c, "check", 0)
        assert c.verdict(0) == "unreadable"

    # -- the deterministic re-derivation ------------------------------------

    def test_the_verdict_is_recomputed_from_the_stored_framings(self):
        """The stored verdict must always follow from the stored framings.

        Without this the block could report SUPPORTED while storing two answers
        that say otherwise, and stability() would count a verdict that its own
        record contradicts.
        """
        c = self.deploy()
        self.mocks(SUPPORT)
        real = S._run_nondet_unsafe

        def lying(leader_fn, validator_fn):
            out = real(leader_fn, validator_fn)
            out["positive"] = "no"        # verdict says supported, answers do not
            return out

        S.gl.vm.run_nondet_unsafe = staticmethod(lying)
        try:
            with pytest.raises(S.UserError, match="does not follow"):
                S.call(c, "check", 0)
        finally:
            S.gl.vm.run_nondet_unsafe = staticmethod(real)
        assert c.stability(0)["checks"] == 0

    def test_a_leader_supplied_reason_is_sanitised_before_storage(self):
        """The reasons are not part of consensus by design, so a leader picks
        them freely. They are cleaned on the way into storage instead."""
        c = self.deploy()
        self.mocks({
            "Does the evidence SUPPORT": {
                "answer": "yes", "because": "<script>x</script>\u0000 fee is 0.4"},
            "Does the evidence CONTRADICT": {"answer": "no", "because": "none"},
        })
        S.call(c, "check", 0)
        stored = c.latest(0)["framings"]["why_supports"]
        assert "<" not in stored and ">" not in stored
        assert "\u0000" not in stored
        assert "fee is 0.4" in stored

    def test_the_view_says_the_reasons_are_leader_supplied(self):
        c = self.deploy()
        self.mocks(SUPPORT)
        S.call(c, "check", 0)
        assert c.latest(0)["reasons_are_leader_supplied"] is True

    # -- stability ---------------------------------------------------------

    def test_stability_accumulates_across_checks(self):
        c = self.deploy()
        self.mocks(BOTH_YES)
        for _ in range(3):
            S.call(c, "check", 0)
        self.mocks(SUPPORT)
        S.call(c, "check", 0)
        s = c.stability(0)
        assert s == {"checks": 4, "supported": 1, "refuted": 0,
                     "unstable": 3, "unstable_pct": 75}

    def test_verdict_is_safe_before_any_check(self):
        c = self.deploy()
        assert c.verdict(0) == "unstable"
        assert c.stability(0)["checks"] == 0


    def test_a_read_with_a_nonexistent_id_is_a_user_error(self):
        """Not a raw IndexError. GenVM reports an uncaught Python exception as
        a contract error, which tells a caller nothing about what went wrong."""
        c = self.deploy()
        for method in ("verdict", "latest", "stability"):
            with pytest.raises(S.UserError, match="no such claim"):
                getattr(c, method)(99)

    def test_a_read_with_a_negative_id_does_not_return_the_last_record(self):
        """The dangerous half. Python list indexing accepts -1 and returns the
        newest claim, so a caller asking for claim -1 would silently receive a
        different claim's verdict and never know."""
        c = self.deploy()
        self.mocks(SUPPORT)
        S.call(c, "check", 0)
        assert c.verdict(0) == "supported"
        for method in ("verdict", "latest", "stability"):
            with pytest.raises(S.UserError, match="no such claim"):
                getattr(c, method)(-1)

    # -- validation --------------------------------------------------------

    @pytest.mark.parametrize(
        "claim,url",
        [
            ("fee", "https://a.example/t"),                     # a fragment
            ("The fee is low." * 40, "https://a.example/t"),     # several claims
            (CLAIM, "ftp://a.example/t"),                        # not http
            (CLAIM, "a.example/t"),                              # no scheme
        ],
    )
    def test_bad_registrations_are_refused(self, claim, url):
        c = S.deploy("contracts/crosscheck.py")
        with pytest.raises(S.UserError):
            S.call(c, "register", claim, url)
        assert c.count() == 0

    def test_out_of_range_ids_are_refused(self):
        c = S.deploy("contracts/crosscheck.py")
        for bad in (0, 5, -1):
            with pytest.raises(S.UserError):
                S.call(c, "check", bad)


# ===========================================================================
# TOLERANCE
# ===========================================================================


class TestAtomicity:
    def test_nothing_is_written_when_a_check_fails(self):
        c = S.deploy("contracts/crosscheck.py")
        S.call(c, "register", CLAIM, "https://a.example/t")
        S.set_mocks(
            leader_pages={"a.example": PAGE}, leader_prompts=SUPPORT,
            validator_pages={"a.example": PAGE}, validator_prompts=REFUTE,
        )
        with pytest.raises(S.UserError):
            S.call(c, "check", 0)
        assert c.stability(0)["checks"] == 0
