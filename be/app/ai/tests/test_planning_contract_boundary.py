"""공개 계약이 내부 구현으로 역참조하거나 두 곳에 정의되지 않게 한다."""
import ast
from pathlib import Path
from typing import get_args

from pydantic import BaseModel

import app.ai as ai
from app.ai import contracts, errors
from app.ai import planning_contracts as previous_path


def test_public_planning_models_and_nested_models_are_owned_by_contracts():
    seen = set()

    def visit(annotation):
        for item in get_args(annotation):
            visit(item)
        if not isinstance(annotation, type) or not issubclass(annotation, BaseModel) or annotation in seen:
            return
        seen.add(annotation)
        assert annotation.__module__ == contracts.__name__, annotation
        for field in annotation.model_fields.values():
            visit(field.annotation)

    for model in (ai.PlanningChatRequest, ai.PlanningPreviewRequest, ai.PlanningPublicResult, ai.PlanningResumeState):
        visit(model)
    assert contracts.RecordLookupResult in seen
    assert contracts.EventPlanPreview in seen


def test_root_contracts_do_not_import_feature_implementations():
    tree = ast.parse(Path(contracts.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert 'features' not in (node.module or '').split('.')
        elif isinstance(node, ast.Import):
            assert all('features' not in alias.name.split('.') for alias in node.names)


def test_old_imports_are_aliases_not_separate_definitions():
    from app.ai.features.planning.agent.state import PlanningDraft
    from app.ai.features.planning.generation.schemas import EventPlanPreview
    from app.ai.features.retrieval.schemas import RecordFact
    assert previous_path.PlanningChatRequest is ai.PlanningChatRequest is contracts.PlanningChatRequest
    assert PlanningDraft is contracts.PlanningDraft
    assert EventPlanPreview is contracts.EventPlanPreview
    assert RecordFact is contracts.RecordFact
    assert ai.PlanningStateError is errors.PlanningStateError
    assert issubclass(ai.PlanningStateError, ValueError)
