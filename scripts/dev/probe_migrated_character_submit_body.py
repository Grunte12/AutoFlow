"""Metadata-only, always-blocked character submit-body probe.

This is a future live *UI* probe, not a generation tool. It uses the repo's
lease-owning :func:`_spike_common.build_client`, selects one exact character,
and blocks the browser network before clicking submit. A DevTools-level
block-all rule remains active until the owned context closes; in-page fetch
and XHR wrappers only return allowlisted metadata and never pass raw bodies,
URLs, prompts, entity/project IDs, or tokens back to Python.

Before a future operator run, first perform the auth-only check
``gflow auth status --profile <profile>`` and pass ``--auth-status-verified``.
This script itself is deliberately not run as part of its implementation.
It never removes the migrated ``reference_entities`` guard and never writes a
capture or report file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Mapping

_ROOT = Path(__file__).resolve().parents[2]
_SAFE_STAGES = frozenset(
    {
        "arguments",
        "preflight",
        "profile",
        "browser",
        "editor",
        "settings",
        "character",
        "submit-button",
        "network-block",
        "self-test",
        "submit",
        "restore",
        "timeout",
    }
)
_SAFE_RPC_IDS = frozenset({"YhhmEf", "eb1hJf", "MZZa6b", "nprQif"})
_PROBE_PROMPT = "Metadata-only character submit probe"
_TOTAL_TIMEOUT_S = 150
_BROWSER_TIMEOUT_S = 75
_STAGE_TIMEOUT_S = 45
_CDP_TIMEOUT_S = 5


class _ProbeFailure(Exception):
    """Internal failure carrying a fixed, safe stage label only."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if stage in _SAFE_STAGES else "timeout"
        super().__init__(self.stage)


class _DiscardWriter:
    """Discard dependency output rather than buffering potentially sensitive logs."""

    def write(self, value: str) -> int:
        return len(value)

    def flush(self) -> None:
        return None


def _safe_failure_line(stage: str, _exception: BaseException | None = None) -> str:
    """Format a failure without ever consulting exception or input contents."""
    safe_stage = stage if stage in _SAFE_STAGES else "unknown"
    return f"probe status=blocked stage={safe_stage}"


def _is_batchexecute(url: str) -> bool:
    """Match the endpoint path, not incidental query text."""
    try:
        path = urllib.parse.unquote(urllib.parse.urlsplit(url).path).casefold().rstrip("/")
    except (TypeError, ValueError):
        return False
    return path.endswith("/data/batchexecute") or path == "data/batchexecute"


def _decoded_body_text(body: str | bytes | None) -> tuple[str, bool]:
    if body is None:
        return "", False
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
    elif isinstance(body, str):
        text = body
    else:
        return "", False
    if not text:
        return "", False
    try:
        form = urllib.parse.parse_qs(text, keep_blank_values=True)
        values = form.get("f.req")
        if values:
            return values[0], True
    except (TypeError, ValueError):
        pass
    return urllib.parse.unquote_plus(text), True


def _safe_rpc_id(url: str, decoded_body: str) -> str | None:
    try:
        values = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("rpcids", [])
        for value in values:
            for candidate in re.split(r"[,;\s]+", value):
                if candidate in _SAFE_RPC_IDS:
                    return candidate
        envelope = json.loads(decoded_body)
        candidate = envelope[0][0][0]
        return candidate if candidate in _SAFE_RPC_IDS else None
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def _summarize_request(
    url: str,
    body: str | bytes | None,
    *,
    expected_entity_id: str,
    expected_project_id: str,
) -> dict[str, str | bool | None]:
    """Compare expected IDs in memory and return only safe booleans/RPC metadata."""
    decoded, body_present = _decoded_body_text(body)
    return {
        "rpc_id": _safe_rpc_id(url, decoded),
        "entity_id_present": bool(expected_entity_id and expected_entity_id in decoded),
        "project_id_present": bool(expected_project_id and expected_project_id in decoded),
        "r2v_model_present": "r2v" in decoded.casefold(),
        "body_present": body_present,
    }


def _blocker_self_test_passed(proof: Mapping[str, object]) -> bool:
    """Require both fake channels to be blocked and neither to reach its tripwire."""
    expected = {
        "fake_requests": 2,
        "fetch_blocked": 1,
        "xhr_blocked": 1,
        "fetch_forwarded": 0,
        "xhr_forwarded": 0,
    }
    return proof.get("self_test_passed") is True and all(
        type(proof.get(key)) is int and proof.get(key) == value
        for key, value in expected.items()
    )


_INSTALL_BLOCKERS_JS = r"""
async (expected) => {
  const state = {
    phase: 'self_test', self_test_passed: false,
    fake_requests: 0, fetch_blocked: 0, xhr_blocked: 0,
    fetch_forwarded: 0, xhr_forwarded: 0, open_forwarded: 0,
    fetch_count: 0, xhr_count: 0, other_blocked_count: 0,
    capture_count: 0,
    last: {rpc_id: null, entity_id_present: false, project_id_present: false,
           r2v_model_present: false, body_present: false}
  };
  const proto = XMLHttpRequest.prototype;
  const originals = {fetch: window.fetch, open: proto.open, send: proto.send};
  const forwarded = {
    fetch: (...args) => {
      state.fetch_forwarded += 1;
      return Promise.resolve({ok: true, status: 204});
    },
    open: function (...args) { state.open_forwarded += 1; },
    send: function (...args) { state.xhr_forwarded += 1; }
  };
  const xhrUrls = new WeakMap();
  const safeRpcIds = new Set(['YhhmEf', 'eb1hJf', 'MZZa6b', 'nprQif']);
  const isBatch = value => {
    try {
      const path = new URL(String(value), location.href).pathname.toLowerCase().replace(/\/$/, '');
      return path.endsWith('/data/batchexecute') || path === 'data/batchexecute';
    } catch (_) { return false; }
  };
  const urlOf = input => (input && typeof input === 'object' && 'url' in input) ? input.url : input;
  const bodyText = async (input, init) => {
    if (init && typeof init.body === 'string') return init.body;
    if (init && init.body instanceof URLSearchParams) return init.body.toString();
    if (input instanceof Request) {
      try { return await input.clone().text(); } catch (_) { return ''; }
    }
    return '';
  };
  const rpcFrom = (url, decoded) => {
    try {
      for (const value of new URL(String(url), location.href).searchParams.getAll('rpcids')) {
        for (const item of value.split(/[,;\s]+/)) if (safeRpcIds.has(item)) return item;
      }
    } catch (_) {}
    try {
      const outer = JSON.parse(decoded);
      const candidate = outer[0][0][0];
      return safeRpcIds.has(candidate) ? candidate : null;
    } catch (_) { return null; }
  };
  const summarize = (url, body) => {
    const raw = typeof body === 'string' ? body : '';
    let decoded = raw;
    try {
      const fReq = new URLSearchParams(raw).get('f.req');
      if (fReq !== null) decoded = fReq;
      else decoded = decodeURIComponent(raw.replace(/\+/g, ' '));
    } catch (_) {}
    state.capture_count += 1;
    state.last = {
      rpc_id: rpcFrom(url, decoded),
      entity_id_present: Boolean(expected.entity_id && decoded.includes(expected.entity_id)),
      project_id_present: Boolean(expected.project_id && decoded.includes(expected.project_id)),
      r2v_model_present: decoded.toLowerCase().includes('r2v'),
      body_present: raw.length > 0
    };
  };
  const fakeResponse = () => Promise.resolve(new Response(null, {status: 204}));
  const wrappedFetch = async function (input, init) {
    const url = urlOf(input);
    const batch = isBatch(url);
    if (state.phase === 'self_test' && batch) {
      state.fetch_blocked += 1;
      return fakeResponse();
    }
    if (state.phase === 'armed') {
      if (batch) {
        state.fetch_count += 1;
        summarize(url, await bodyText(input, init));
      } else {
        state.other_blocked_count += 1;
      }
      return fakeResponse();
    }
    if (batch) {
      state.fetch_blocked += 1;
      return fakeResponse();
    }
    return forwarded.fetch.apply(this, arguments);
  };
  const wrappedOpen = function (method, url) {
    xhrUrls.set(this, String(url));
    return forwarded.open.apply(this, arguments);
  };
  const wrappedSend = function (body) {
    const url = xhrUrls.get(this) || '';
    const batch = isBatch(url);
    if (state.phase === 'self_test' && batch) {
      state.xhr_blocked += 1;
      return;
    }
    if (state.phase === 'armed') {
      if (batch) {
        state.xhr_count += 1;
        summarize(url, body);
      } else {
        state.other_blocked_count += 1;
      }
      return;
    }
    if (batch) {
      state.xhr_blocked += 1;
      return;
    }
    return forwarded.send.apply(this, arguments);
  };
  window.fetch = wrappedFetch;
  proto.open = wrappedOpen;
  proto.send = wrappedSend;
  const restore = () => {
    if (window.fetch === wrappedFetch) window.fetch = originals.fetch;
    if (proto.open === wrappedOpen) proto.open = originals.open;
    if (proto.send === wrappedSend) proto.send = originals.send;
    if (window.__gflowCharacterBodyProbe === api) delete window.__gflowCharacterBodyProbe;
    return true;
  };
  const arm = () => { state.phase = 'armed'; return true; };
  const snapshot = () => ({
    self_test_passed: state.self_test_passed,
    fake_requests: state.fake_requests,
    fetch_blocked: state.fetch_blocked,
    xhr_blocked: state.xhr_blocked,
    fetch_forwarded: state.fetch_forwarded,
    xhr_forwarded: state.xhr_forwarded,
    fetch_count: state.fetch_count,
    xhr_count: state.xhr_count,
    other_blocked_count: state.other_blocked_count,
    capture_count: state.capture_count,
    last: state.last
  });
  const api = {restore, arm, snapshot};
  window.__gflowCharacterBodyProbe = api;
  try {
    const fakeUrl = 'https://gflow-probe.invalid/data/batchexecute?rpcids=MZZa6b';
    await window.fetch(fakeUrl, {method: 'POST', body: 'synthetic-only'});
    state.fake_requests += 1;
    const fakeXhr = new XMLHttpRequest();
    fakeXhr.open('POST', fakeUrl);
    fakeXhr.send('synthetic-only');
    state.fake_requests += 1;
    state.self_test_passed = state.fake_requests === 2 &&
      state.fetch_blocked === 1 && state.xhr_blocked === 1 &&
      state.fetch_forwarded === 0 && state.xhr_forwarded === 0;
    if (state.self_test_passed) {
      forwarded.fetch = (...args) => originals.fetch.apply(window, args);
      forwarded.open = function (...args) { return originals.open.apply(this, args); };
      forwarded.send = function (...args) { return originals.send.apply(this, args); };
      state.phase = 'ready';
    }
    return snapshot();
  } catch (_) {
    return snapshot();
  }
}
"""

_ARM_BLOCKERS_JS = """() => {
  const api = window.__gflowCharacterBodyProbe;
  return api ? api.arm() : false;
}"""

_SNAPSHOT_BLOCKERS_JS = """() => {
  const api = window.__gflowCharacterBodyProbe;
  return api ? api.snapshot() : null;
}"""

_RESTORE_BLOCKERS_JS = """() => {
  const api = window.__gflowCharacterBodyProbe;
  return api ? api.restore() : true;
}"""


def _configure_quiet_logging() -> None:
    """Silence dependency logs in this one-shot script; only our safe line is emitted."""
    logging.disable(logging.CRITICAL)
    try:
        import structlog

        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL + 1),
            logger_factory=structlog.ReturnLoggerFactory(),
            cache_logger_on_first_use=False,
        )
    except ImportError:
        pass


def _load_runtime() -> tuple[Any, Any, Any, Any, Any]:
    source = str(_ROOT / "src")
    dev = str(_ROOT / "scripts" / "dev")
    if source not in sys.path:
        sys.path.insert(0, source)
    if dev not in sys.path:
        sys.path.insert(0, dev)
    from _spike_common import build_client, resolve_profile_dir
    from gflow_cli.api.transports.migrated_composer import (
        COMPOSER,
        MigratedComposer,
        _ligature,
    )
    from gflow_cli.api.video import GenerateVideoRequest, Mode

    return (
        build_client,
        resolve_profile_dir,
        COMPOSER,
        MigratedComposer,
        (GenerateVideoRequest, Mode, _ligature),
    )


async def _run_probe(args: argparse.Namespace) -> dict[str, Any]:
    stage = "profile"
    patch_attempted = False
    page: Any | None = None
    try:
        _configure_quiet_logging()
        (
            build_client,
            resolve_profile_dir,
            composer_selector,
            composer_type,
            video_types,
        ) = _load_runtime()
        GenerateVideoRequest, Mode, ligature = video_types
        discard = _DiscardWriter()
        with redirect_stdout(discard), redirect_stderr(discard):
            profile_dir = resolve_profile_dir(args.profile)

        stage = "browser"
        async with build_client(profile_dir, headless=False) as client:
            page = client.page
            composer = composer_type()
            stage = "editor"
            await asyncio.wait_for(
                composer.ensure_editor(page, args.project_id), timeout=_STAGE_TIMEOUT_S
            )

            stage = "settings"
            request = GenerateVideoRequest(
                prompt=_PROBE_PROMPT,
                mode=Mode.R2V,
                duration=8,
                count=1,
                reference_entities=(args.entity_id,),
                reference_entity_names=(args.entity_name,),
            )
            await asyncio.wait_for(
                composer.apply_video_settings(page, request), timeout=_STAGE_TIMEOUT_S
            )

            stage = "character"
            await asyncio.wait_for(
                composer.attach_character_entities(
                    page,
                    entity_ids=(args.entity_id,),
                    names=(args.entity_name,),
                    clear=True,
                ),
                timeout=_STAGE_TIMEOUT_S,
            )
            chips_ok = await asyncio.wait_for(
                page.evaluate(
                    """(expected) => {
                      const chips = [...document.querySelectorAll('.mention-chip')];
                      return chips.length === 1 && chips.every(c =>
                        c.getAttribute('data-reference-type') === 'entity' &&
                        c.getAttribute('data-entity-id') === expected);
                    }""",
                    args.entity_id,
                ),
                timeout=5,
            )
            if chips_ok is not True:
                raise _ProbeFailure("character")

            await asyncio.wait_for(
                page.locator(composer_selector).first.click(timeout=4000), timeout=5
            )
            await asyncio.wait_for(page.keyboard.insert_text(f" {_PROBE_PROMPT}"), timeout=5)
            submit = page.locator("button").filter(has=ligature(page, "arrow_forward")).first
            submit_count = await asyncio.wait_for(submit.count(), timeout=5)
            submit_enabled = (
                await asyncio.wait_for(submit.is_enabled(), timeout=5) if submit_count else False
            )
            if not submit_count or not submit_enabled:
                raise _ProbeFailure("submit-button")

            stage = "network-block"
            context = getattr(client, "_context", None)
            if context is None:
                raise _ProbeFailure(stage)
            cdp = await asyncio.wait_for(context.new_cdp_session(page), timeout=_CDP_TIMEOUT_S)
            await asyncio.wait_for(cdp.send("Network.enable"), timeout=_CDP_TIMEOUT_S)
            await asyncio.wait_for(
                cdp.send("Network.setBlockedURLs", {"urls": ["*"]}),
                timeout=_CDP_TIMEOUT_S,
            )

            stage = "self-test"
            patch_attempted = True
            proof = await asyncio.wait_for(
                page.evaluate(
                    _INSTALL_BLOCKERS_JS,
                    {"entity_id": args.entity_id, "project_id": args.project_id},
                ),
                timeout=5,
            )
            if not isinstance(proof, dict) or not _blocker_self_test_passed(proof):
                raise _ProbeFailure(stage)

            armed = await asyncio.wait_for(page.evaluate(_ARM_BLOCKERS_JS), timeout=5)
            if armed is not True:
                raise _ProbeFailure(stage)

            stage = "submit"
            await asyncio.wait_for(submit.click(timeout=4000), timeout=6)
            await asyncio.sleep(1.0)
            snapshot = await asyncio.wait_for(page.evaluate(_SNAPSHOT_BLOCKERS_JS), timeout=5)
            if not isinstance(snapshot, dict) or snapshot.get("self_test_passed") is not True:
                raise _ProbeFailure(stage)
            last = snapshot.get("last")
            if not isinstance(last, dict):
                last = {}
            # Restrict the report to the exact safe schema. No request bodies, IDs,
            # prompt text, URLs, tokens, or exception details cross into this dict.
            result = {
                "status": "blocked",
                "self_test_passed": True,
                "browser_network_blocked": True,
                "capture_count": _safe_count(snapshot.get("capture_count")),
                "fetch_count": _safe_count(snapshot.get("fetch_count")),
                "xhr_count": _safe_count(snapshot.get("xhr_count")),
                "other_blocked_count": _safe_count(snapshot.get("other_blocked_count")),
                "rpc_id": last.get("rpc_id") if last.get("rpc_id") in _SAFE_RPC_IDS else None,
                "entity_id_present": last.get("entity_id_present") is True,
                "project_id_present": last.get("project_id_present") is True,
                "r2v_model_present": last.get("r2v_model_present") is True,
                "body_present": last.get("body_present") is True,
            }
            return result
    except _ProbeFailure:
        raise
    except asyncio.TimeoutError:
        raise _ProbeFailure(stage if stage in _SAFE_STAGES else "timeout") from None
    except SystemExit:
        raise _ProbeFailure("profile") from None
    except Exception:
        raise _ProbeFailure(stage if stage in _SAFE_STAGES else "timeout") from None
    finally:
        restore_failed = False
        if patch_attempted and page is not None:
            try:
                restored = await asyncio.wait_for(page.evaluate(_RESTORE_BLOCKERS_JS), timeout=5)
                restore_failed = restored is not True
            except Exception:
                # The CDP block-all rule remains attached to the owned context until
                # build_client closes it, even if page-side restoration cannot finish.
                restore_failed = True
        if restore_failed:
            raise _ProbeFailure("restore") from None


def _safe_count(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise _ProbeFailure("arguments")


def main(argv: list[str] | None = None) -> int:
    parser = _SafeArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--entity-id", required=True)
    parser.add_argument("--entity-name", required=True)
    parser.add_argument(
        "--auth-status-verified",
        action="store_true",
        help="confirm that `gflow auth status --profile <profile>` already reported authenticated",
    )
    try:
        args = parser.parse_args(argv)
        if not args.auth_status_verified:
            raise _ProbeFailure("preflight")
        discard = _DiscardWriter()
        with redirect_stdout(discard), redirect_stderr(discard):
            result = asyncio.run(asyncio.wait_for(_run_probe(args), timeout=_TOTAL_TIMEOUT_S))
    except _ProbeFailure as exc:
        print(_safe_failure_line(exc.stage), file=sys.stderr, flush=True)
        return 2
    except asyncio.TimeoutError:
        print(_safe_failure_line("timeout"), file=sys.stderr, flush=True)
        return 2
    except Exception:
        print(_safe_failure_line("timeout"), file=sys.stderr, flush=True)
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
