"""Run inside the final Designer image to refresh existing deterministic exports."""
import json
import sys
from designer import pipeline, store
from designer.contracts import Deck, DeckPlan, SlideSpec, Scene
from designer.parse.package import load_package
from designer.export.pptx_deck import export_pptx
from designer.export import convert
from designer.export.html import render_deck
from designer.export.html_image import render_deck_images
from designer.export.sources import export_source_package

deck_id, variant = sys.argv[1:]
state=store.load_deck_state(deck_id,variant)
assert state and state["status"]=="done", "Cannot reexport an incomplete job"
package=store.design_system_dir(state["design_system_id"])
ds=load_package(package)
deck=Deck(id=deck_id,variant=variant,design_system_id=ds.id,
          plan=DeckPlan.model_validate(state["plan"]),
          specs=[SlideSpec.model_validate(s) for s in state["specs"]],
          scenes=[Scene.model_validate(s) for s in state["scenes"]])
directory=store.deck_variant_files_dir(deck_id,variant)
pptx=directory/"deck.pptx"
export_pptx(deck.specs,ds,package,pptx)
pdf=directory/"deck.pdf"
convert.to_pdf(pptx,pdf)
pngs=pipeline._save_slide_images(deck_id,variant,pptx,len(deck.specs),lambda _:None,pdf)
assert len(pngs)==len(deck.specs)
(directory/"deck.markup.html").write_text(render_deck(deck,ds,package),encoding="utf-8")
(directory/"deck.html").write_text(render_deck_images(deck,ds,[p.read_bytes() for p in pngs]),encoding="utf-8")
export_source_package(deck.plan, directory)
print(json.dumps({"deckId":deck_id,"variant":variant,"slides":len(pngs),"planUnchanged":True,"modelCalls":0}))
