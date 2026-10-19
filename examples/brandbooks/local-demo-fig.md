# Native Figma fixture provenance

`local-demo.fig` is an original synthetic test document generated locally with
`node scripts/create-demo-fig.mjs` from the frontend directory.

The installed MIT-licensed `openfig-core@0.4.1` supplies its empty document/schema;
the script adds original named color swatches, Play font declarations (no font
binaries), and a six-column stretch layout grid on a 1280×720 frame. It uses
`encodeFigParts`, Node's Zstd compressor, `assembleCanvasFig`, and `createFigZip`.
This is a ZIP containing a real Kiwi/Zstd `canvas.fig`, not renamed JSON, and is
round-tripped with `parseFig`. No remote design or artwork is included. It has
not been opened or visually validated in the Figma application.

Expected recovered data: opaque fills `0D1429` and `268CF2`; font family Play;
explicit heading 48 px = 36 pt and body 32 px = 24 pt; six columns, offset 64 px,
gutter 24 px. The browser computes the original file SHA-256 before conversion.
Original node names assign the explicit `background`, `accent`, `heading`, and
`body` roles. Files lacking role names retain unclassified tokens; roles and
missing style properties are never reconstructed by a model.

Import is offline in a worker (20 MiB input, 12-second timeout). The original
`.fig` is not uploaded; extracted JSON contains its name/hash and observations.
Only visible opaque solid fills, concrete text font values and unambiguous
explicit horizontal stretch column grids are mapped. Gradients, transparent
fills, unresolved variables, arbitrary layout semantics and embedded font files
are not recovered.
