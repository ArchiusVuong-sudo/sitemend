#!/bin/sh
# Starts the Claude Code CLI with an allowlisted environment and nothing else.
# The SDK passes the real binary in SITEMEND_REAL_CLI; env -i drops every other
# inherited variable (including CLAUDECODE and CLAUDE_CODE_*).
real="$SITEMEND_REAL_CLI"
if [ -z "$real" ]; then
  echo "SITEMEND_REAL_CLI is not set" >&2
  exit 127
fi
exec /usr/bin/env -i \
  PATH="$PATH" HOME="$HOME" USER="$USER" LANG="${LANG:-en_US.UTF-8}" TMPDIR="${TMPDIR:-/tmp}" \
  ${ANTHROPIC_API_KEY:+"ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY"} \
  "$real" "$@"
