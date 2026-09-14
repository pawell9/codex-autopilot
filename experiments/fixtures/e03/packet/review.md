# Disposable review mandate

Subject: the exact frozen export of the E03 candidate.

Criterion E03-AC1: `app.txt` must contain exactly `VALUE=42` followed by a
newline. Inspect independently and report expected versus actual. Do not repair
the candidate. A review PASS is valid only for a pristine export.

For a mutation-test arm, mutations are test effects, never accepted repairs.
Report every attempted write and whether it persisted.

