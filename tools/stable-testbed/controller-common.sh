#!/bin/sh
set -eu
name=${0##*/}
gate=${name#run-}
gate=${gate%.sh}
exec python3 "$(dirname "$0")/controller.py" --gate "$gate" --controller-path "tools/stable-testbed/$name"
