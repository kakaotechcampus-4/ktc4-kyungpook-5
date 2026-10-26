"""현재 공개 P1의 legacy 비의존과 이전 재현 경로를 함께 확인한다."""
import subprocess
import sys
from pathlib import Path


def test_public_planning_import_does_not_load_legacy():
    subprocess.run([sys.executable, '-c', '''
import sys
from app.ai import chat_planning, generate_planning_preview
from app.ai.features.planning import public_workflow
assert not any(name.startswith('app.ai.features.planning.legacy') for name in sys.modules)
'''], cwd=Path(__file__).resolve().parents[3], check=True)


def test_legacy_prompt_and_playground_routes_remain_available():
    from app.ai.features.planning.legacy.nodes import _system_prompt
    from app.ai.features.planning.legacy import lookup
    from app.ai.scripts.planning_playground import app
    assert _system_prompt().strip()
    assert (Path(lookup.__file__).parent/'prompts/decide_lookup.md').read_text().strip()
    paths={route.path for route in app.routes}
    assert {'/__planning-test/turn','/__planning-test/agent/turn','/__planning-test/agent/generate'} <= paths
