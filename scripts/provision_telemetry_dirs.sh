#!/bin/bash
# provision_telemetry_dirs.sh - Safe shared telemetry directory provisioning.
#
# Trusted deployment owner only. Rejects symlinks and non-directories before any
# mkdir/chmod. Creates the parent with mkdir -p -- and users with mkdir -- when
# absent, then applies exact portable modes 0755 / 1777.
#
# Paths are normalized by stripping one-or-more trailing slashes while preserving
# a lone root token ("/"). Empty, ".", and "/" are rejected so this helper never
# chmods root or creates /users.
#
# Usage:
#   . scripts/provision_telemetry_dirs.sh
#   provision_shared_telemetry_dirs "/ads_storage/autobench/telemetry"
#
# Or as a script:
#   scripts/provision_telemetry_dirs.sh [/path/to/telemetry]

# Strip trailing slashes but keep a legitimate root token as "/".
_normalize_telemetry_dir() {
  local p="${1-}"
  while [ "$p" != "/" ] && [ "$p" != "${p%/}" ]; do
    p="${p%/}"
  done
  printf '%s' "$p"
}

provision_shared_telemetry_dirs() {
  local raw="${1-}"
  local TELEMETRY_DIR
  TELEMETRY_DIR="$(_normalize_telemetry_dir "$raw")"
  local USERS_DIR="${TELEMETRY_DIR}/users"

  case "$TELEMETRY_DIR" in
    "" )
      printf 'ERROR: TELEMETRY_DIR is empty (refusing unsafe root)\n' >&2
      return 1
      ;;
    "." )
      printf 'ERROR: TELEMETRY_DIR is "." (refusing unsafe root)\n' >&2
      return 1
      ;;
    "/" )
      printf 'ERROR: TELEMETRY_DIR is "/" (refusing unsafe root; would create /users)\n' >&2
      return 1
      ;;
  esac

  # -L/-e inspect the normalized path itself (test(1) has no --); mkdir/chmod use -- below.
  if [ -L "$TELEMETRY_DIR" ]; then
    printf 'ERROR: TELEMETRY_DIR is a symlink (refusing): %s\n' "$TELEMETRY_DIR" >&2
    return 1
  fi
  if [ -e "$TELEMETRY_DIR" ] && [ ! -d "$TELEMETRY_DIR" ]; then
    printf 'ERROR: TELEMETRY_DIR is not a directory (refusing): %s\n' "$TELEMETRY_DIR" >&2
    return 1
  fi
  if [ ! -e "$TELEMETRY_DIR" ]; then
    mkdir -p -- "$TELEMETRY_DIR" || {
      printf 'ERROR: failed to create TELEMETRY_DIR: %s\n' "$TELEMETRY_DIR" >&2
      return 1
    }
  fi
  if [ -L "$TELEMETRY_DIR" ] || [ ! -d "$TELEMETRY_DIR" ]; then
    printf 'ERROR: TELEMETRY_DIR must be a real directory after create: %s\n' "$TELEMETRY_DIR" >&2
    return 1
  fi

  if [ -L "$USERS_DIR" ]; then
    printf 'ERROR: users entry is a symlink (refusing): %s\n' "$USERS_DIR" >&2
    return 1
  fi
  if [ -e "$USERS_DIR" ] && [ ! -d "$USERS_DIR" ]; then
    printf 'ERROR: users entry is not a directory (refusing): %s\n' "$USERS_DIR" >&2
    return 1
  fi
  if [ ! -e "$USERS_DIR" ]; then
    mkdir -- "$USERS_DIR" || {
      printf 'ERROR: failed to create users directory: %s\n' "$USERS_DIR" >&2
      return 1
    }
  fi
  if [ -L "$USERS_DIR" ] || [ ! -d "$USERS_DIR" ]; then
    printf 'ERROR: users must be a real directory after create: %s\n' "$USERS_DIR" >&2
    return 1
  fi

  chmod -- 0755 "$TELEMETRY_DIR" || {
    printf 'ERROR: chmod 0755 failed for %s\n' "$TELEMETRY_DIR" >&2
    return 1
  }
  chmod -- 1777 "$USERS_DIR" || {
    printf 'ERROR: chmod 1777 failed for %s\n' "$USERS_DIR" >&2
    return 1
  }
  return 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -euo pipefail
  _dir="${1:-${AUTOBENCH_TELEMETRY_DIR:-/ads_storage/autobench/telemetry}}"
  provision_shared_telemetry_dirs "$_dir"
fi
