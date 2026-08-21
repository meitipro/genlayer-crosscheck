"""
Integration tests, run against GenLayer Studio with gltest.

    pip install genlayer-test
    gltest --network studionet tests/test_integration.py

These are slower than tests/test_logic.py and they prove something different:
that the contracts deploy, that storage round-trips, that the deterministic
gates fire, and that the whole leader-plus-validator cycle completes.

The web page and the model are both mocked, so a run is deterministic and needs
no network. Mocks match by substring against the message the runtime builds, so
the keys below are fragments of the prompts in contracts/.
"""

import pytest

# gltest is only needed for this file. Skip cleanly when it is absent so that
# `pytest tests/` works out of the box on a machine with nothing installed but
# pytest, and still runs everything in test_logic.py and test_e2e.py.
gltest = pytest.importorskip(
    "gltest",
    reason="integration tests need genlayer-test and a running Studio: "
           "pip install genlayer-test, then gltest --network studionet",
)
from gltest import get_contract_factory                      # noqa: E402
from gltest.assertions import (                              # noqa: E402
    tx_execution_succeeded,
    tx_execution_failed,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


LIVE_PAGE = (
    "Status page. The mainnet contracts are verified on the explorer. "
    "Withdrawal fee is 0.4 percent. Visitors today: 1,204. "
    "Treasury balance: 50,000 GEN. Last updated one minute ago."
) * 3

EMPTY_PAGE = "  "


def web(mapping):
    """Build a mocked web response table keyed by url."""
    return {"nondet_web_render": mapping}


def llm(mapping):
    """Build a mocked prompt response table keyed by prompt substring."""
    return {"nondet_exec_prompt": mapping}


def merge(*ds):
    out = {}
    for d in ds:
        out.update(d)
    return out

class TestCrosscheck:
    @pytest.fixture
    def contract(self):
        factory = get_contract_factory("Contract", contract_file="contracts/crosscheck.py")
        return factory.deploy(args=[])

    def _register(self, contract, claim="The withdrawal fee is under one percent."):
        tx = contract.register(args=[claim, "https://a.example/terms"])
        assert tx_execution_succeeded(tx)

    def test_mirrored_answers_produce_supported(self, contract):
        self._register(contract)
        mocks = merge(
            web({"a.example": LIVE_PAGE}),
            llm({
                "Does the evidence SUPPORT": {"answer": "yes", "because": "fee is 0.4 percent"},
                "Does the evidence CONTRADICT": {"answer": "no", "because": "nothing contradicts it"},
            }),
        )
        tx = contract.check(args=[0], mock_response=mocks)
        assert tx_execution_succeeded(tx)
        assert contract.verdict(args=[0]).call() == "supported"

    def test_mirrored_the_other_way_produces_refuted(self, contract):
        self._register(contract)
        mocks = merge(
            web({"a.example": LIVE_PAGE}),
            llm({
                "Does the evidence SUPPORT": {"answer": "no", "because": "fee is 4 percent"},
                "Does the evidence CONTRADICT": {"answer": "yes", "because": "page says 4 percent"},
            }),
        )
        tx = contract.check(args=[0], mock_response=mocks)
        assert tx_execution_succeeded(tx)
        assert contract.verdict(args=[0]).call() == "refuted"

    def test_a_model_that_agrees_with_both_framings_is_caught(self, contract):
        """The failure this primitive exists for.

        A single-framing contract asks "does it support?", hears yes, and
        records SUPPORTED. Here the mirror question also hears yes, the two
        answers cannot both be true, and the network agrees on UNSTABLE.
        """
        self._register(contract)
        mocks = merge(
            web({"a.example": LIVE_PAGE}),
            llm({
                "Does the evidence SUPPORT": {"answer": "yes", "because": "seems so"},
                "Does the evidence CONTRADICT": {"answer": "yes", "because": "also seems so"},
            }),
        )
        tx = contract.check(args=[0], mock_response=mocks)
        assert tx_execution_succeeded(tx)
        assert contract.verdict(args=[0]).call() == "unstable"

    def test_unreadable_evidence_is_its_own_verdict(self, contract):
        self._register(contract)
        mocks = merge(web({"a.example": EMPTY_PAGE}), llm({}))
        tx = contract.check(args=[0], mock_response=mocks)
        assert tx_execution_succeeded(tx)
        assert contract.verdict(args=[0]).call() == "unreadable"

    def test_stability_record_accumulates(self, contract):
        self._register(contract)
        unstable = merge(
            web({"a.example": LIVE_PAGE}),
            llm({
                "Does the evidence SUPPORT": {"answer": "yes", "because": "x"},
                "Does the evidence CONTRADICT": {"answer": "yes", "because": "y"},
            }),
        )
        for _ in range(2):
            contract.check(args=[0], mock_response=unstable)
        s = contract.stability(args=[0]).call()
        assert s["checks"] == 2
        assert s["unstable"] == 2
        assert s["unstable_pct"] == 100

    def test_verdict_view_is_safe_before_any_check(self, contract):
        self._register(contract)
        assert contract.verdict(args=[0]).call() == "unstable"

    def test_a_fragment_is_not_a_claim(self, contract):
        tx = contract.register(args=["fee", "https://a.example/terms"])
        assert tx_execution_failed(tx)

    def test_non_http_evidence_is_refused(self, contract):
        tx = contract.register(
            args=["The withdrawal fee is under one percent.", "ftp://a.example/terms"]
        )
        assert tx_execution_failed(tx)


# ---------------------------------------------------------------------------
# TOLERANCE
# ---------------------------------------------------------------------------
