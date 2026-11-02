The first image is the reference. Each following image is one candidate, labelled just before it ({{labels}}). A candidate image is a 2x2 grid of the same 3D model rendered from four front views on a white background: front-left and front-right at eye level (top row), from below and from above (bottom row).

Which candidate is the most faithful 3D reproduction of the reference in these views? Give every candidate a penalty 0-10:
0 = Perfect match to reference
3 = Minor issues (slight shape differences, missing small details)
5 = Moderate issues (wrong style, significant details missing)
7 = Major issues (wrong category but related)
10 = Completely wrong object

Judge object identity, silhouette and proportions, the side shown and the layout of parts, colors and visible text. Ignore lighting and the background; do not reward complexity that the reference does not show.

Output: {"penalties": {"<label>": <0-10>, ...}, "reason": "<brief>"}
