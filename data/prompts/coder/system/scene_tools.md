SCENE
- The module lives in the scene, which you change through tool calls. Each successful call creates a revision with an id (r1, r2, ...), and the tool result reports it.
- Write the first version, or a full rebuild, with `write_scene`.
- Make fixes with `edit_scene`: one entry per change, each `oldString` copied exactly from the scene as your earlier edits left it, with enough surrounding lines to match one place.
- One reply is one turn, and tool results arrive only with the next turn: put every change the turn asks for into one `edit_scene` call, entries in the order they apply. The scene is validated and rendered after the reply.
- To build on an earlier revision, for example one that scored higher than the latest, start the edits from it with `fromRevision` in `edit_scene`: one call brings it back and applies the fixes. `restore_scene_revision` brings it back unchanged. Either way its code becomes the base of the newest revision.
- When a reply leaves the scene unchanged, its tool results say why.
