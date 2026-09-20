"""План презентации по брифу. Владелец: задача T-04."""
from designer.contracts import DeckPlan
from designer.llm.client import LlmClient


def make_plan(brief: str, purpose: str, audience: str, slide_count: int | None, client: LlmClient) -> DeckPlan:
    raise NotImplementedError("T-04")
