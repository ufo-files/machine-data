# Epistemic qualifier candidates

`config/epistemic_qualifiers.json` is the versioned policy shared by the review queue and downstream graph builds. `scripts/annotate_epistemic_qualifiers.py` creates a review queue for language that changes how a nearby statement should be read. It never edits transcripts, deletes claims, changes raw mention counts, or asserts speaker identity. Downstream graph builds may use the published weights for derived prominence and relationship ranking while continuing to publish the unmodified counts beside them.

The v1 categories are explicit conjecture, evidence not reviewed, reported hearsay, explicit uncertainty, knowledge gaps, limited recall, and lower-confidence speaker inference. Every record retains the exact qualifier, original segment, proposed claim scope, timestamp, source path, and an unresolved speaker attribution. Cross-segment scope is deliberately capped at lower confidence because TSV transcripts do not consistently identify speakers.

Run it over selected source collections:

```sh
python3 scripts/annotate_epistemic_qualifiers.py \
  Area52-Investigations UAP-Gerb Weaponized-Podcast American-Alchemy \
  --output .state/epistemic-qualifier-candidates.jsonl
```

The generated queue belongs in `.state/` and is not committed. Downstream publication should present the qualifier alongside—not instead of—the source statement. Bare phrases such as “I think” receive a deliberately modest discount because they often express emphasis, preference, or conversational rhythm rather than factual doubt. These heuristic weights affect graph ordering, not the certainty of separately reviewed claims.
