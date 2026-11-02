You see two 3D models rendered from {{angle}}.
The reference image shows the target object.

Which model is a more faithful 3D reproduction of the reference?

Penalty 0-10:
0 = Perfect match to reference
3 = Minor issues (slight shape differences, missing small details)
5 = Moderate issues (wrong style, significant details missing)
7 = Major issues (wrong category but related)
10 = Completely wrong object

Output: {"penalty_1": <0-10>, "penalty_2": <0-10>, "issues": "<brief>"}
