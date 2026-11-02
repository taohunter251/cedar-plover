PIPELINE
- Every turn starts fresh: it brings the reference photo and the task, and you keep no memory of earlier turns.
- The first turn asks for the complete module. Later turns bring the render of the newest revision and its full code, and ask you to rewrite the whole module better.
- Each module goes to an automatic validator (any violation scores 0), then to the renderer. A rejected module comes back with the validator's failures and its code to fix.
- A render is a 3x2 grid on a white background under neutral light. Top row: front-left and front-right at eye level, the front from slightly below. Bottom row: the front from above, a side view and the back. The first four are exactly the views the judge compares first.
