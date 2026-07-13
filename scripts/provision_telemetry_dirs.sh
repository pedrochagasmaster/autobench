#!/bin/bash
# provision_telemetry_dirs.sh - Safe shared telemetry directory provisioning.
#
# Trusted deployment owner only. Rejects symlinks and non-directories before any
# mkdir/chmod. Creates the parent with mkdir -p -- and users with mkdir -- when
# absent, then applies exact portable modes 0755 / 1777.
#
# Paths must be absolute. One-or-more trailing slashes are stripped while
# preserving a lone root token ("/"). Empty, ".", "/", relative paths, and any
# lexical path component exactly "." or ".." are rejected before filesystem
# mutation so this helper never chmods an unintended root or creates /users.
# Repeated internal slashes are allowed (harmless).
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

# Return 0 when any lexical component is exactly "." or "..".
_telemetry_dir_has_dot_component() {
  local p="$1"
  local rest="${p#/}"
  local comp
  while [ -n "$rest" ]; do
    case "$rest" in
      */*)
        comp="${rest%%/*}"
        rest="${rest#*/}"
        ;;
      *)
        comp="$rest"
        rest=""
        ;;
    esac
    # Empty components from repeated slashes are harmless.
    if [ "$comp" = "." ] || [ "$comp" = ".." ]; then
      return 0
    fi
  done
  return 1
}

# Walk every lexical absolute prefix from / to target. Reject symlink or
# non-directory ancestors. Missing components are allowed. Does not chmod
# ancestors and does not require deploy-uid ownership of system parents.
_reject_symlink_or_nondir_ancestors() {
  local target="$1"
  local rest="${target#/}"
  local cur=""
  local comp
  while [ -n "$rest" ]; do
    case "$rest" in
      */*)
        comp="${rest%%/*}"
        rest="${rest#*/}"
        ;;
      *)
        comp="$rest"
        rest=""
        ;;
    esac
    [ -n "$comp" ] || continue
    cur="${cur}/${comp}"
    if [ -L "$cur" ]; then
      printf 'ERROR: path component is a symlink (refusing): %s\n' "$cur" >&2
      return 1
    fi
    if [ -e "$cur" ] && [ ! -d "$cur" ]; then
      printf 'ERROR: path component is not a directory (refusing): %s\n' "$cur" >&2
      return 1
    fi
  done
  return 0
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

  case "$TELEMETRY_DIR" in
    /*) ;;
    *)
      printf 'ERROR: TELEMETRY_DIR must be an absolute path (refusing): %s\n' "$TELEMETRY_DIR" >&2
      return 1
      ;;
  esac

  if _telemetry_dir_has_dot_component "$TELEMETRY_DIR"; then
    printf 'ERROR: TELEMETRY_DIR contains a "." or ".." dot component (refusing): %s\n' "$TELEMETRY_DIR" >&2
    return 1
  fi

  # Reject intermediate symlink/non-dir ancestors before any mkdir/chmod.
  _reject_symlink_or_nondir_ancestors "$TELEMETRY_DIR" || return 1

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
  # Re-walk after create to close simple create races (symlink swapped in).
  _reject_symlink_or_nondir_ancestors "$TELEMETRY_DIR" || return 1
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
  _reject_symlink_or_nondir_ancestors "$USERS_DIR" || return 1
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
