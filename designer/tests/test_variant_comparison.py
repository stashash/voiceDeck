from PIL import Image
from designer import store
from designer.api.schemas import DeckVariantState
from designer.contracts import DeckPlan, SlideIntent, SlideKind
from designer.variant_comparison import compare_exported_variants


def test_actual_pixel_duplicates_and_changed_exports(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path))
    plan = DeckPlan(title="T", purpose="test", slides=[SlideIntent(id="s", kind=SlideKind.title, title="T")])
    variants = {c: DeckVariantState(status="done", design_system_id="ds", plan=plan) for c in "abc"}
    for code, color in (("a", "white"), ("b", "white"), ("c", "black")):
        path = store.deck_variant_slides_dir("deck", code) / "slide-001.png"
        Image.new("RGB", (40, 30), color).save(path)
    compare_exported_variants("deck", variants)
    assert variants["b"].comparison_to_a["exact_duplicate"]
    assert variants["b"].comparison_to_a["basis"] == "exported_pixels"
    assert not variants["c"].comparison_to_a["near_duplicate"]
    Image.new("RGB", (40, 30), "red").save(store.deck_variant_slides_dir("deck", "b") / "slide-001.png")
    compare_exported_variants("deck", variants)
    assert not variants["b"].comparison_to_a["exact_duplicate"]


def test_stale_export_does_not_claim_visual_comparison(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path))
    plan = DeckPlan(title="T", purpose="test", slides=[SlideIntent(id="s", kind=SlideKind.title, title="T")])
    variants = {c: DeckVariantState(status="done", design_system_id="ds", plan=plan) for c in "ab"}
    variants["b"].revision = "new"
    variants["b"].images_revision = "old"
    for c in variants:
        Image.new("RGB", (40, 30), "white").save(store.deck_variant_slides_dir("deck", c) / "slide-001.png")
    compare_exported_variants("deck", variants)
    assert variants["b"].comparison_to_a is None


def test_axis_does_not_claim_denser_layout_when_nothing_merged():
    from designer.layout.variants import actual_axis
    plan = DeckPlan(title="T", purpose="test", slides=[SlideIntent(id="s", kind=SlideKind.title, title="T")])
    assert "не применилось" in actual_axis("b", plan, plan)
    assert "зависят" in actual_axis("c", plan, plan)
