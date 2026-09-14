#!/bin/sh
set -eu

fixture_root="$1"
trace="$fixture_root/trace.log"
tmp_return="$fixture_root/return.tmp"
final_return="$fixture_root/return.json"

printf 'writer-start\n' > "$trace"
i=1
while [ "$i" -le 12 ]; do
  printf 'step=%s\n' "$i" >> "$trace"
  sleep 1
  i=$((i + 1))
done

printf '%s\n' \
  '{"attempt_id":"e02-interruption","status":"DONE","marker":"E02_RETURN_76d9c4af","steps":12}' \
  > "$tmp_return"
mv "$tmp_return" "$final_return"
printf 'return-published\n' >> "$trace"

