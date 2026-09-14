# E03-M fixture intent v1

Goal: verify the manual G5 fallback end-to-end on a frozen candidate.

Requirement R-E03M-1: the candidate application must report `VALUE=42` in
`app.txt`.

Observable criterion C-E03M-1: inspect the pristine candidate export and verify
that `app.txt` contains exactly `VALUE=42`; a reviewer must report independent
evidence and a structured outcome.

Exclusion: no deployment, merge, network service, credentials, or changes to
the authoritative repository/control root are in scope.

