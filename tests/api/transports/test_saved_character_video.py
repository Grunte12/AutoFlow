"""Exact saved-Character binding and null-ack attribution regressions."""

import json
from urllib.parse import urlencode

import pytest

from gflow_cli.api.transports.saved_character_video import (
    attributed_character_record,
    character_submission,
)
from gflow_cli.errors import WireFormatError

PROJECT = "00000000-0000-4000-8000-000000000001"
ENTITY = "00000000-0000-4000-8000-000000000002"
MEDIA = "00000000-0000-4000-8000-000000000003"
WORKFLOW = "00000000-0000-4000-8000-000000000004"
DOC = [None, None, [[[None, [None, None, [ENTITY, "Goofy"]]], ["Hello"]]]]


def body(entities=None, project=PROJECT):
    spec = [
        DOC,
        None,
        "abra_r2v_8s",
        1,
        None,
        None,
        None,
        None,
        None,
        [[e] for e in (entities if entities is not None else [ENTITY])],
    ]
    payload = [[spec], [None, 22, None, None, None, project]]
    return urlencode({"f.req": json.dumps([[["MZZa6b", json.dumps(payload), None, "generic"]]])})


def record(doc=DOC, project=PROJECT, media=MEDIA, workflow=WORKFLOW):
    details = [None] * 14
    details[6] = [None, None, [doc]]
    details[8] = [3]
    video = [None] * 9
    video[8] = "https://example.com/video.mp4"
    return [media, project, workflow, None, None, details, None, [video, None, [media]]]


@pytest.mark.parametrize(
    "entities,project",
    [([], PROJECT), ([MEDIA], PROJECT), ([ENTITY, ENTITY], PROJECT), ([ENTITY], MEDIA)],
)
def test_refuses_wrong_wire_binding(entities, project):
    with pytest.raises(WireFormatError):
        character_submission(body(entities, project), PROJECT, (ENTITY,))


def test_exact_new_prompt_record_uses_native_media_workflow_identity():
    submission = character_submission(body(), PROJECT, (ENTITY,))
    rec = attributed_character_record([record()], submission, frozenset())
    assert rec is not None
    assert rec.media_id == MEDIA and rec.workflow_id == WORKFLOW
    assert rec.is_done


def test_stale_composer_text_is_blocked_before_billing():
    with pytest.raises(WireFormatError):
        character_submission(body(), PROJECT, (ENTITY,), "different intended prompt")
    assert character_submission(body(), PROJECT, (ENTITY,), "Hello")


@pytest.mark.parametrize(
    "rows,baseline",
    [
        ([record()], frozenset({MEDIA})),
        ([record(doc=["unrelated"])], frozenset()),
        ([record(project=MEDIA)], frozenset()),
    ],
)
def test_never_adopts_old_or_unrelated_record(rows, baseline):
    submission = character_submission(body(), PROJECT, (ENTITY,))
    assert attributed_character_record(rows, submission, baseline) is None


def test_ambiguous_exact_new_records_fail_without_choosing_first():
    submission = character_submission(body(), PROJECT, (ENTITY,))
    with pytest.raises(WireFormatError, match="ambiguous"):
        attributed_character_record([record(), record(media=ENTITY)], submission, frozenset())
