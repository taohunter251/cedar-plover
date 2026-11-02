PIPELINE
- The first turn brings the reference photo. You build the module over several turns.
- After each reply that changes the module, its newest revision goes to an automatic validator (any violation scores 0), then to the renderer, and the next turn brings the outcome:
  - a rejection: the validator's failures for that revision;
  - a render: the grid of that revision in the judge's four front views (front-left, front-right, from below, from above), with a critic's review of it: a score (0..1, higher is better), the scores of the revisions reviewed so far, aspects to preserve and issues to fix. Compare the grid with the photo yourself first; the review supports that comparison.
- After a reply that leaves the module unchanged, the next turn asks again for the same changes.
