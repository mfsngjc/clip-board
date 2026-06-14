# Repository Maintenance Rule

Before changing Clip Board, read `ARCHITECTURE.md`.

Every functional, interaction, model, schema, shortcut, packaging, file-association,
or test change must update the relevant section of `ARCHITECTURE.md` and append an
entry to its change log. A change is not complete until the documentation and
verification notes match the implementation.

Keep serialized models free of Qt types, keep media processing outside widgets,
and prefer undoable commands for reversible project edits.
