#!/usr/bin/env sh
# Source this file to run Dispatch against local fakes.

DISPATCH_MOCKS_FILE=${BASH_SOURCE:-$0}
DISPATCH_MOCKS_DIR=$(CDPATH= cd -- "$(dirname -- "$DISPATCH_MOCKS_FILE")" && pwd)
export DISPATCH_MOCKS_DIR
export DISPATCH_DATA_ROOT="${DISPATCH_DATA_ROOT:-/tmp/ads_storage/${USER:-dispatch}}"
export DISPATCH_MOCK_SCENARIO="${DISPATCH_MOCK_SCENARIO:-happy_path}"
export DISPATCH_MOCK_STATE_DIR="${DISPATCH_MOCK_STATE_DIR:-/tmp/dispatch_mock_state}"
export MAILHOST="${MAILHOST:-127.0.0.1:2525}"
export DISPATCH_SCR_DIR="${DISPATCH_SCR_DIR:-$(CDPATH= cd -- "$DISPATCH_MOCKS_DIR/.." && pwd)/scr}"
export PATH="$DISPATCH_MOCKS_DIR/bin:$PATH"

mkdir -p "$DISPATCH_DATA_ROOT/.dispatch/jobs" "$DISPATCH_MOCKS_DIR/sent_emails" "$DISPATCH_MOCK_STATE_DIR"

if [ -z "${DISPATCH_SMTPD_PID:-}" ] || ! kill -0 "$DISPATCH_SMTPD_PID" 2>/dev/null; then
  python3 "$DISPATCH_MOCKS_DIR/smtpd.py" "$DISPATCH_MOCKS_DIR/sent_emails" >/tmp/dispatch_mock_smtpd.log 2>&1 &
  export DISPATCH_SMTPD_PID=$!
fi

cat <<BANNER
Dispatch dev mode enabled
  DISPATCH_DATA_ROOT=$DISPATCH_DATA_ROOT
  DISPATCH_MOCK_SCENARIO=$DISPATCH_MOCK_SCENARIO
  MAILHOST=$MAILHOST
  SMTP pid=$DISPATCH_SMTPD_PID
BANNER
