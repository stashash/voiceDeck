"""Strict, bounded edits committed as one revision and one undo entry."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from designer import edit, store
from designer.contracts import TextStyle
from designer.edit_runtime import lock


Identifier = Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]
Color = Annotated[str, Field(min_length=6, max_length=6, pattern=r"^[0-9A-Fa-f]{6}$")]
Coordinate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=True)]


class VoiceBatchStyle(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    size_pt: float | None = Field(default=None, ge=6, le=144, allow_inf_nan=False)
    bold: bool | None = None
    italic: bool | None = None
    color: Color | None = None
    align: Literal["left", "center", "right"] | None = None

    @model_validator(mode="after")
    def supplied_properties(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Supply at least one non-null text style property")
        return self


class VoiceBatchOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    element_id: Identifier
    box: list[Coordinate] | None = Field(default=None, min_length=4, max_length=4)
    style: VoiceBatchStyle | None = None
    fill: Color | None = None

    @field_validator("box")
    @classmethod
    def bounded_box(cls, value):
        if value is not None:
            edit._element_box(tuple(value))
        return value

    @model_validator(mode="after")
    def supplied_properties(self):
        supplied = self.model_fields_set - {"element_id"}
        if not supplied or any(getattr(self, key) is None for key in supplied):
            raise ValueError("Supply at least one non-null box, style or fill")
        return self


class VoiceBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_revision: str
    target_slide_id: Identifier
    operations: list[VoiceBatchOperation] = Field(min_length=1, max_length=64)

    @field_validator("operations")
    @classmethod
    def unique_targets(cls, value):
        if len({operation.element_id for operation in value}) != len(value):
            raise ValueError("Each element may appear only once in a voice batch")
        return value


class VoiceBatchConflict(ValueError):
    """The revision or stable slide identity no longer matches the request."""


def apply_voice_batch(deck_id: str, variant: str, number: int, payload: VoiceBatch) -> dict:
    with lock(deck_id, variant):
        state = edit._load(deck_id, variant)
        if (state.raw.get("revision") or "") != payload.expected_revision:
            raise VoiceBatchConflict("The document has changed; the voice batch was not saved")
        try:
            index = edit._slide_index(state, number)
        except edit.SlideNotFound as exc:
            raise VoiceBatchConflict("The selected slide has changed; the voice batch was not saved") from exc
        scene, spec = state.scenes[index], state.specs[index]
        if scene.slide_id != payload.target_slide_id:
            raise VoiceBatchConflict("The selected slide has changed; the voice batch was not saved")

        elements = {element.id: element for element in scene.elements}
        changes = []
        for operation in payload.operations:
            old = elements.get(operation.element_id)
            if old is None:
                raise ValueError("Selected element was not found on this slide")
            if operation.style is not None and old.type != "text":
                raise ValueError("Font properties are supported only for text elements")
            if operation.fill is not None and old.type != "shape":
                raise ValueError("fill is supported only for shape elements")
            # Split number/caption elements still address one native PPTX shape.
            if old.source_shape_id is not None and any(
                other.id != old.id and other.source_shape_id == old.source_shape_id
                and (other.id == old.id + "c" or old.id == other.id + "c")
                for other in scene.elements
            ):
                raise ValueError("This number and caption share one native shape; edit a separate text element")

            new = old.model_copy(deep=True)
            if operation.box is not None:
                new.box = tuple(operation.box)
            if operation.style is not None:
                original_style = old.style or TextStyle()
                properties = operation.style.model_dump(exclude_unset=True)
                if "color" in properties:
                    color = properties["color"].upper()
                    properties["color"] = (original_style.color
                                           if (original_style.color or "").upper() == color else color)
                style = original_style.model_copy(update=properties)
                if style != original_style:
                    new.style = style
            if operation.fill is not None and operation.fill.upper() != (old.fill or "").upper():
                new.fill = operation.fill.upper()
            if new != old:
                changes.append((old, new))

        if not changes:
            return state.raw
        for old, new in changes:
            edit._save_element(scene, spec, old, new)
        findings = edit._checks(state, {spec.slide_id})
        edit._snapshot(state)
        edit._persist(state, findings)
        return store.load_deck_state(deck_id, variant)
