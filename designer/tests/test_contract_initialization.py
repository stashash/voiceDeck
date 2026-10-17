import os
import subprocess
import sys


def test_slide_spec_is_complete_on_fresh_import():
    # Подпроцесс не видит pythonpath из настроек pytest: передаём ему тот же путь поиска.
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join(p for p in sys.path if p)}
    subprocess.run(
        [sys.executable, '-c',
         'from designer.contracts import SlideSpec; '
         'assert SlideSpec.__pydantic_complete__; '
         'SlideSpec.model_validate(dict(slide_id="s1", pattern_id="p1"))'],
        check=True, capture_output=True, text=True, env=env,
    )
