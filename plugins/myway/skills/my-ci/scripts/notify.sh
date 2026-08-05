#!/usr/bin/env bash
set -uo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# ============================================================
# Notify — CLI wrapper for use inside pipeline YAML
# ============================================================
# Usage: echo "what happened" | notify.sh <level> <title>
#   level: error | warning | success | info
#
# No-op unless MYCI_NOTIFY_WEBHOOK is set; always exits 0 so it can sit in a
# `cmd || (notify; exit 1)` failure handler without masking the real status.
# Payload shape via MYCI_NOTIFY_STYLE: generic (default) | feishu | slack.
# ============================================================

myci_notify "${1:?usage: notify.sh <level> <title>}" "${2:?usage: notify.sh <level> <title>}"
exit 0
