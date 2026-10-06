"""Offline safety contract for the metadata-only migrated character probe."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.dev.probe_migrated_character_submit_body import (
    _ARM_BLOCKERS_JS,
    _INSTALL_BLOCKERS_JS,
    _RESTORE_BLOCKERS_JS,
    _blocker_self_test_passed,
    _is_batchexecute,
    _safe_failure_line,
    _summarize_request,
)


def test_summary_keeps_only_allowlisted_metadata() -> None:
    entity_id = "11111111-2222-4333-8444-555555555555"
    project_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    private_prompt = "PROMPT_SENTINEL_do_not_print"
    private_token = "TOKEN_SENTINEL_do_not_print"
    body = (
        "f.req=%5B%5B%5B%22MZZa6b%22%2C%22%5B%5B%5C%22"
        + entity_id
        + "%5C%22%5D%2C%5C%22"
        + project_id
        + "%20abra_r2v_8s%20"
        + private_prompt
        + "%20"
        + private_token
        + "%5C%22%5D%22%5D%5D%5D"
    )
    url = "https://probe.invalid/data/batchexecute?token=" + private_token

    summary = _summarize_request(
        url,
        body,
        expected_entity_id=entity_id,
        expected_project_id=project_id,
    )

    assert summary == {
        "rpc_id": "MZZa6b",
        "entity_id_present": True,
        "project_id_present": True,
        "r2v_model_present": True,
        "body_present": True,
    }
    rendered = repr(summary)
    assert entity_id not in rendered
    assert project_id not in rendered
    assert private_prompt not in rendered
    assert private_token not in rendered
    assert "probe.invalid" not in rendered


def test_summary_does_not_echo_unrecognized_rpc_ids() -> None:
    private_rpc = "opaque-private-rpc"
    summary = _summarize_request(
        "https://example.invalid/data/batchexecute?rpcids=" + private_rpc,
        "private prompt and token",
        expected_entity_id="entity",
        expected_project_id="project",
    )

    assert summary["rpc_id"] is None
    assert private_rpc not in repr(summary)


def test_batchexecute_detection_checks_path_not_query_text() -> None:
    assert _is_batchexecute("https://example.invalid/data/batchexecute?x=1")
    assert not _is_batchexecute("https://example.invalid/not-batch?next=/data/batchexecute")


def test_blocker_round_trip_requires_both_channels_and_zero_forwarding() -> None:
    proof = {
        "self_test_passed": True,
        "fake_requests": 2,
        "fetch_blocked": 1,
        "xhr_blocked": 1,
        "fetch_forwarded": 0,
        "xhr_forwarded": 0,
    }
    assert _blocker_self_test_passed(proof)

    for changed in (
        {**proof, "fetch_blocked": 0},
        {**proof, "xhr_blocked": 0},
        {**proof, "fetch_forwarded": 1},
        {**proof, "xhr_forwarded": 1},
        {**proof, "fake_requests": 1},
        {**proof, "self_test_passed": False},
    ):
        assert not _blocker_self_test_passed(changed)
    assert not _blocker_self_test_passed({"private": "raw payload"})


def test_failure_line_is_stage_only_and_never_includes_exception_text() -> None:
    secret = "prompt entity uuid token URL"
    rendered = _safe_failure_line("submit", RuntimeError(secret))

    assert rendered == "probe status=blocked stage=submit"
    assert secret not in rendered
    assert _safe_failure_line("secret-stage", RuntimeError(secret)) == (
        "probe status=blocked stage=unknown"
    )


def test_real_headless_blocker_round_trip_on_offline_data_url() -> None:
    """Exercise the shipped JS in an ephemeral browser with all network disabled."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise unittest.SkipTest("Playwright is not installed; no browser was launched") from None

    with sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        launch_args = [
            "--disable-background-networking",
            "--disable-component-update",
            "--no-first-run",
        ]
        if executable.is_file():
            browser = playwright.chromium.launch(headless=True, args=launch_args)
        else:
            # The Chrome channel uses Playwright's fresh temporary profile. Never
            # connect to or reuse the user's persistent browser profile.
            browser = playwright.chromium.launch(
                headless=True,
                channel="chrome",
                args=launch_args,
            )
        try:
            context = browser.new_context()
            context.set_offline(True)
            page = context.new_page()
            page.goto("data:text/html,<html><body>offline probe</body></html>")
            page.evaluate(
                """() => {
                  const proto = XMLHttpRequest.prototype;
                  const originals = {fetch: window.fetch, open: proto.open, send: proto.send};
                  const trips = {fetch: 0, send: 0, open: 0};
                  window.__probeTestBaseline = {originals, trips};
                  window.fetch = function () {
                    trips.fetch += 1;
                    return Promise.resolve({ok: true, status: 204});
                  };
                  proto.open = function () { trips.open += 1; };
                  proto.send = function () { trips.send += 1; };
                }"""
            )

            entity_id = "11111111-2222-4333-8444-555555555555"
            project_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
            proof = page.evaluate(
                _INSTALL_BLOCKERS_JS,
                {"entity_id": entity_id, "project_id": project_id},
            )
            assert proof == {
                "self_test_passed": True,
                "fake_requests": 2,
                "fetch_blocked": 1,
                "xhr_blocked": 1,
                "fetch_forwarded": 0,
                "xhr_forwarded": 0,
                "fetch_count": 0,
                "xhr_count": 0,
                "other_blocked_count": 0,
                "capture_count": 0,
                "last": {
                    "rpc_id": None,
                    "entity_id_present": False,
                    "project_id_present": False,
                    "r2v_model_present": False,
                    "body_present": False,
                },
            }
            assert page.evaluate(_ARM_BLOCKERS_JS) is True

            request_body = page.evaluate(
                """({entity_id, project_id}) => new URLSearchParams({
                  'f.req': JSON.stringify([[['MZZa6b', JSON.stringify([
                    entity_id, project_id, 'abra_r2v_8s',
                    'PROMPT_SENTINEL', 'TOKEN_SENTINEL'
                  ])]]])
                }).toString()""",
                {"entity_id": entity_id, "project_id": project_id},
            )
            synthetic_url = "https://gflow-probe.invalid/data/batchexecute?rpcids=MZZa6b"
            snapshot = page.evaluate(
                """async ({url, body}) => {
                  await window.fetch(url, {method: 'POST', body});
                  const xhr = new XMLHttpRequest();
                  xhr.open('POST', url);
                  xhr.send(body);
                  return window.__gflowCharacterBodyProbe.snapshot();
                }""",
                {"url": synthetic_url, "body": request_body},
            )
            assert snapshot["capture_count"] == 2
            assert snapshot["fetch_count"] == 1
            assert snapshot["xhr_count"] == 1
            assert snapshot["last"] == {
                "rpc_id": "MZZa6b",
                "entity_id_present": True,
                "project_id_present": True,
                "r2v_model_present": True,
                "body_present": True,
            }
            rendered = json.dumps(snapshot)
            assert entity_id not in rendered
            assert project_id not in rendered
            assert "PROMPT_SENTINEL" not in rendered
            assert "TOKEN_SENTINEL" not in rendered
            assert "gflow-probe.invalid" not in rendered

            tripwires = page.evaluate("""() => ({...window.__probeTestBaseline.trips})""")
            assert tripwires["fetch"] == 0
            assert tripwires["send"] == 0
            assert page.evaluate(_RESTORE_BLOCKERS_JS) is True
            restored = page.evaluate(
                """() => {
                  const proto = XMLHttpRequest.prototype;
                  const baseline = window.__probeTestBaseline;
                  const ok = window.fetch !== baseline.originals.fetch &&
                    proto.open !== baseline.originals.open &&
                    proto.send !== baseline.originals.send;
                  window.fetch = baseline.originals.fetch;
                  proto.open = baseline.originals.open;
                  proto.send = baseline.originals.send;
                  delete window.__probeTestBaseline;
                  return ok;
                }"""
            )
            assert restored is True
            context.close()
        finally:
            browser.close()
