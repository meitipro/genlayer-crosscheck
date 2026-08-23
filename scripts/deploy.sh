#!/usr/bin/env bash
#
# deploy.sh — deploy Crosscheck and leave real consensus evidence on the explorer.
#
#   ./scripts/deploy.sh studionet
#
# A contract page showing only a deploy transaction proves the file compiles and
# nothing else. This script deploys AND exercises the contract, so the explorer
# shows method calls with the leader's proposal and the validators' votes beside
# them. That page is the strongest single artifact in a submission.
#
# Requires: npm i -g genlayer

set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NETWORK="${1:-studionet}"
gold() { printf '\033[33m%s\033[0m\n' "$*"; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }

gold "Deploying Crosscheck to $NETWORK"
genlayer network set "$NETWORK"

dim "linting"
PYTHONIOENCODING=utf-8 genvm-lint lint contracts/crosscheck.py

ADDR=$(genlayer deploy --contract contracts/crosscheck.py \
       | grep -oE '0x[0-9a-fA-F]{40}' | head -1)
gold "deployed at $ADDR"

dim "register() a claim, frozen against one evidence page"
genlayer write "$ADDR" register --args \
  "This domain is reserved for use in illustrative examples in documents." \
  "https://example.com" >/dev/null

dim "check()    two mirrored prompts in one block"
genlayer write "$ADDR" check --args 0

dim "latest()   the verdict and both framings that produced it"
genlayer call "$ADDR" latest --args 0

# A second claim, deliberately vague, so the refusal path is on chain too. A
# contract page showing only successes is a weaker demonstration than one
# showing the primitive decline to answer.
dim "register() a vague claim, to leave an unstable verdict on chain"
genlayer write "$ADDR" register --args \
  "This page is broadly considered to be quite useful for most purposes." \
  "https://example.com" >/dev/null
genlayer write "$ADDR" check --args 1 || true
genlayer call "$ADDR" stability --args 1

cat <<EOF

  Contract:  $ADDR
  Explorer:  https://explorer-studio.genlayer.com/address/$ADDR

Open that page before submitting. It must show a Deploy transaction AND at
least one method call with a Consensus Result beside it.

EOF
