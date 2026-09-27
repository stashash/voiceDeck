import subprocess
import sys


def test_slide_spec_is_complete_on_fresh_import():
    subprocess.run(
        [sys.executable, '-c',
         'from designer.contracts import SlideSpec; '
         'assert SlideSpec.__pydantic_complete__; '
         'SlideSpec.model_validate(dict(slide_id="s1", pattern_id="p1"))'],
        check=True, capture_output=True, text=True,
    )
