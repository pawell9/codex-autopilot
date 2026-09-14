#!/bin/sh
set -eu

fixture_root="$1"
printf '%s\n' "$$" > "$fixture_root/pid"
printf '%s\n' '{"attempt_id":"e02-cancel","status":"DONE"' > "$fixture_root/return.tmp"
printf 'partial-written\n' > "$fixture_root/trace.log"
sleep 30
printf '%s\n' '}' >> "$fixture_root/return.tmp"
mv "$fixture_root/return.tmp" "$fixture_root/return.json"
printf 'return-published\n' >> "$fixture_root/trace.log"

