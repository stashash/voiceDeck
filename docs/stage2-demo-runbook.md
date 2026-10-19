# Stage 2 live demo

`examples/build-stage2.py` sends the seven committed `semantic_stage2` fixtures as one bundle, chooses the first renderable candidate per returned dataset, materializes those seven choices together, and runs all three variants (`a`, `b`, `c`) for each of three supplied PowerPoint templates. A 201-row reference table is split into readable pages of seven body rows (the native PPTX table renderer limit), with every source row and its original line number retained in provenance. It saves nine PDFs, per-variant run manifests and slide contact sheets under `artifacts/stage2-demo/generated/`.

Start the Designer API and ensure its configured model and PDF/image export tools are available. Then run from the repository root (Python must have Pillow installed):

```powershell
python examples/build-stage2.py `
  --template 'C:\path\to\template-one.pptx' `
  --template 'C:\path\to\template-two.pptx' `
  --template 'C:\path\to\template-three.pptx'
```

For the separately required unknown-template run, pass one public PPTX with `--foreign-template`; this adds one A-variant run after the nine challenge outputs. To run only that extra check after the nine outputs already exist, use `--only-foreign --foreign-template <path>`; saved plans and insights are reused. `artifacts/stage2-demo/sources/README.md` records the external 90s Consulting Strategy Slides source and CC BY 4.0 attribution used for this local demo.

Set `DESIGNER_BASE_URL` or pass `--base-url` when the API is not at `http://127.0.0.1:8000`. `--output` changes the generated artifact directory. HTTP request timeout defaults to 90 seconds; background generation timeout is 30 minutes and can be changed with `--generation-timeout`. The script exits with an error if an API call fails, a variant does not finish, a PDF or slide image is absent, or the final PDF count is not exactly nine.

The script assumes the root API routes `POST /insights/plan` (`files[]`, `goal` multipart fields), `POST /insights/plan/materialize-bundle` (`bundle_id`, JSON `selections` multipart fields), `POST /design-systems` (PPTX file), and `POST /decks` (JSON). It polls `GET /decks/{deck_id}`, retrieves variant PDFs and slide images from `/decks/{deck_id}/{variant}/files/deck.pdf` and `/decks/{deck_id}/{variant}/slides/{number}.png`, and gets the per-variant run manifest from `GET /decks/{deck_id}/run`. Template files are operator supplied because the fixture set contains data files only. IDs are always taken from live responses.

Outputs include `dataset-plan.json`, `materialized-insights.json`, `run-manifest.json`, then one folder per uploaded design-system ID with its API `run.json`, plus one subfolder per variant containing `deck.pdf`, slide PNGs, and `contact-sheet.png`. The API currently exposes `/decks/{id}/run` for the default variant (`a`); the top-level demo manifest records all three variant runs. The unknown-template run is marked separately from the nine required challenge combinations. Fixture values are synthetic and must be presented as such.
