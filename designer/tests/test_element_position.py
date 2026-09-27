from types import SimpleNamespace
import pytest
from designer import edit
from designer.contracts import Element, Scene, SlideSpec

def test_move_clamps_preserves_anchor_and_snapshots(monkeypatch):
    element = Element(id='s1', type='text', box=(.1,.2,.3,.1), source_shape_id=3)
    state = SimpleNamespace(plan=SimpleNamespace(slides=[None]), scenes=[Scene(slide_id='a',pattern_id='p',elements=[element])], specs=[SlideSpec(slide_id='a',pattern_id='p')])
    saved=[]
    monkeypatch.setattr(edit,'_load',lambda *args: state)
    monkeypatch.setattr(edit,'_snapshot',lambda s: saved.append(s.scenes[0].elements[0].box))
    monkeypatch.setattr(edit,'_checks',lambda *args: [])
    monkeypatch.setattr(edit,'_persist',lambda *args: None)
    edit.move_element('test','a',1,'s1',.1,0)
    assert element.box == pytest.approx((.2,.2,.3,.1))
    edit.move_element('test','a',1,'s1',1,-1)
    assert element.box == pytest.approx((.7,0,.3,.1))
    assert state.specs[0].element_positions['s1'].original_box == (.1,.2,.3,.1)
    assert len(saved)==2
    edit.move_element('test','a',1,'s1',align='center')
    assert element.box == pytest.approx((.35,.45,.3,.1))
    with pytest.raises(edit.ElementNotFound): edit.move_element('test','a',1,'absent',.1,0)
    assert len(saved)==3
