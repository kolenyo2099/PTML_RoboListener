#!/bin/bash
cd "$(dirname "$0")"
./run.sh
status=$?
if [ "$status" -ne 0 ]; then
  echo
  echo "RadioWatch could not start (exit code $status). See the message above."
  read -r -p "Press Return to close this window..." _
fi
