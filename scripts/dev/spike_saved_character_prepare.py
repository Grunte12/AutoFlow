"""Prepare existing Characters and capture the submit shape WITHOUT sending it.

No uploads, entity changes or generation. Every known generation RPC is intercepted
and aborted before reaching Flow. A correct chip proves only attachment; the aborted
request proves only its wire shape. Neither proves terminal attribution.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from gflow_cli.api.client import FlowApiClient
from gflow_cli import auth
from gflow_cli.api.video import GenerateVideoRequest, Mode, Aspect, VideoModel
from gflow_cli.api.transports.migrated_composer import MigratedComposer, SUBMIT_RPCS, _ligature
from gflow_cli.api.transports.native_character_ui import _read_project_payload
from gflow_cli.api.transports.native_character import parse_native_characters
from gflow_cli.api.transports.saved_character_video import character_submission


def safe_shape(value):
    if isinstance(value,list):
        return [safe_shape(v) for v in value]
    if isinstance(value,str):
        if re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',value):
            return value
        if re.fullmatch(r'[a-z0-9_]{1,70}',value):
            return value
        return '<text>'
    return value if value is None or type(value) in (bool,int,float) else '<object>'


async def main(args):
    pairs=list(zip(args.entity,args.name,strict=True))
    findings={'generation_sent':False,'entities_verified':False}
    async with FlowApiClient(profile_dir=auth.profile_dir(args.profile),headless=True) as client:
        page=client._page
        assert page is not None
        project_payload=await _read_project_payload(page,args.project,timeout_s=20)
        findings['project_shape']=safe_shape(project_payload)
        native=parse_native_characters(project_payload,args.project)
        current={row.character.entity_id:row.character.display_name for row in native}
        assert all(current.get(e)==n for e,n in pairs), 'Existing native Characters must match'
        findings['entities_verified']=True
        if args.read_media:
            rows=[row for row in project_payload[2] if row[0]==args.read_media]
            assert len(rows)==1 and rows[0][1]==args.project
            doc=rows[0][5][6][2][0]
            def text_leaves(node):
                if not isinstance(node,list): return []
                if len(node)==1 and isinstance(node[0],str): return [node[0]]
                return [s for child in node for s in text_leaves(child)]
            print(json.dumps({'media_id':rows[0][0],'workflow_id':rows[0][2],
                'prompt_text':''.join(text_leaves(doc)), 'rich_prompt':doc},ensure_ascii=False))
            return
        composer=MigratedComposer()
        await composer.ensure_editor(page,args.project)
        req=GenerateVideoRequest(prompt='An affectionate young couple on their cream sofa. Both faces clearly visible.',mode=Mode.R2V,aspect=Aspect.PORTRAIT,model=VideoModel.OMNI_FLASH,duration=8,reference_entities=tuple(args.entity),reference_entity_names=tuple(args.name))
        await composer.apply_video_settings(page,req)
        await composer.attach_character_entities(page,entity_ids=tuple(args.entity),names=tuple(args.name))
        findings['chips']=await composer.read_chips(page)
        await composer.send_prompt(page,req.prompt,append=True)
        captured=asyncio.Event()
        async def intercept(route,request):
            if request.method=='POST':
                raw=parse_qs(request.post_data or '').get('f.req',[''])[0]
                try: rows=json.loads(raw)
                except ValueError: rows=[]
                rpcids=parse_qs(urlsplit(request.url).query).get('rpcids',[])
                if any(r in SUBMIT_RPCS for part in rpcids for r in part.split(',')) or any(r in raw for r in SUBMIT_RPCS):
                    character_submission(request.post_data or '',args.project,tuple(args.entity),req.prompt)
                    findings['wire_binding_verified']=True
                    findings['submit_envelope']=safe_shape(rows)
                    # Decode nested JSON payloads before redaction; never keep tokens.
                    for group in rows:
                        for row in group:
                            if isinstance(row,list) and len(row)>1 and row[0] in SUBMIT_RPCS:
                                try: findings['submit_payload']=safe_shape(json.loads(row[1]))
                                except (ValueError,TypeError): pass
                    await route.abort()
                    captured.set()
                    return
            if request.method == 'POST':
                # No unknown write may escape a zero-credit submit probe.
                await route.abort()
            else:
                await route.continue_()
        await page.route('**/data/batchexecute*',intercept)
        try:
            submit=page.locator('button').filter(has=_ligature(page,'arrow_forward')).first
            await submit.click(timeout=5000)
            await asyncio.wait_for(captured.wait(),15)
            findings['submit_aborted']=True
        finally:
            await page.unroute('**/data/batchexecute*',intercept)
            out=Path(args.output)
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_text(json.dumps(findings,ensure_ascii=False,indent=2))
            print(json.dumps({k:v for k,v in findings.items() if k!='project_shape'},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',required=True)
    parser.add_argument('--project',required=True)
    parser.add_argument('--entity',action='append',required=True)
    parser.add_argument('--name',action='append',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--read-media')
    asyncio.run(main(parser.parse_args()))
