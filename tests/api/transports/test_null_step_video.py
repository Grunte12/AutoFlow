"""Oct6 read-only as29s capture: optional workflow-step marker omitted."""

import copy
import json
from pathlib import Path

import pytest

from gflow_cli.api.transports.batchexecute import generation_record
from gflow_cli.errors import WireFormatError


def captured():
    return json.loads(
        (Path(__file__).parents[2] / "fixtures/migrated_null_step_video.json").read_text()
    )


@pytest.mark.parametrize("rpc", ["eb1hJf", "nprQif", "MZZa6b", "as29s", "jwpduf"])
def test_omitted_step_marker_keeps_measured_video_identity(rpc):
    wire = captured()
    record = generation_record(rpc, [None, 552, [["metadata"]], [[wire]]])
    assert (record.workflow_id, record.project_id, record.media_id) == tuple(wire[:3])
    assert record.is_done and record.size_bytes == 2608862
    assert record.video_url == wire[7][0][8]


@pytest.mark.parametrize("status", [2, 6, 7])
def test_pending_and_failed_null_marker_videos(status):
    wire = captured()
    wire[5][8] = [status]
    wire[5][10] = None
    wire[5][13] = None
    wire[7][0][8] = None
    record = generation_record("jwpduf", wire)
    assert record.status == status
    assert record.is_running == (status in {2, 6})


@pytest.mark.parametrize("damage", ["image", "marker", "status", "workflow", "metadata"])
def test_null_marker_is_not_a_license_to_adopt_arbitrary_uuids(damage):
    wire = captured()
    if damage == "image":
        wire[6] = [None, [None], [720, 1280]]
        wire = wire[:7]
    elif damage == "marker":
        wire[3] = "unmeasured"
    elif damage == "status":
        wire[5][8] = ["3"]
    elif damage == "workflow":
        wire[7][2][0] = wire[2]
    else:
        wire = wire[:6]
    with pytest.raises(WireFormatError):
        generation_record("as29s", wire)


def test_multiple_distinct_records_are_ambiguous_without_identity_filter():
    first = captured()
    other = copy.deepcopy(first)
    other[0] = "11111111-1111-4111-8111-111111111111"
    other[7][2][0] = other[0]
    with pytest.raises(WireFormatError):
        generation_record("jwpduf", [first, other])
    found = generation_record("jwpduf", [other, first], workflow_id=first[0], project_id=first[1])
    assert found.workflow_id == first[0]


def test_unrelated_project_is_not_adopted():
    with pytest.raises(WireFormatError):
        generation_record("as29s", captured(), project_id="11111111-1111-4111-8111-111111111111")
