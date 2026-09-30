#!/usr/bin/env bash
# Compatibility endpoint for the retired remote-pipe installer.

set -euo pipefail

cat >&2 <<'EOF'
✗ The curl|bash installer has been retired for supply-chain safety.

This script never downloads, updates, or executes repository code. Install from
an explicitly reviewed revision instead:

  git clone https://github.com/mgrody1/agentic_coding_stack.git
  cd agentic_coding_stack/gpt-as-subagent
  # Inspect install.sh and requirements.lock, then run:
  ./install.sh

For Codex, run `bash adapters/codex/install.sh` from that same reviewed checkout.
EOF

exit 1
