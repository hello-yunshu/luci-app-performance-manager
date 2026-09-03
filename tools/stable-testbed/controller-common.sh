#!/bin/sh
set -eu
name=${0##*/}
gate=${name#run-}
gate=${gate%.sh}
case "$gate" in
  core-only) gate=target-core-only ;;
  full) gate=target-full ;;
  mutation) gate=target-mutation ;;
esac
exec python3 "$(dirname "$0")/controller.py" --gate "$gate" --controller-path "tools/stable-testbed/$name"
