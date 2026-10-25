"""Actual campaign main-loop/native pixels and mission collapse acceptance.

Hidden ordinary main.py AST loop, stock campaign data and SDL input; isolated persistence.
No replacement renderer. Run under tools.render.verify_star_occlusion.run's deadline.
"""
from __future__ import annotations
import argparse
import ast
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=800)
    args = parser.parse_args()
    out = args.out.resolve()
    assert not out.exists(), 'Use a fresh evidence directory'
    from tools.render.capture_native_notification_hud_game import require_no_owner_game
    require_no_owner_game()
    out.mkdir(parents=True)
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import pygame
    from OpenGL import GL
    from PIL import Image
    from render import menus
    from game.net.replay import state_checksum
    sandbox = out/'user'
    (sandbox/'saves').mkdir(parents=True)
    # Isolate saves, not the shipped catalogue: USER_DIR also resolves visual packs.
    (sandbox/'visual_packs').symlink_to(ROOT/'visual_packs', target_is_directory=True)
    settings = dict(menus.DEFAULT_SETTINGS, resolution=f'{args.width}x{args.height}',
                    fullscreen=False, music_volume=0., sfx_volume=0., autosave=False,
                    cinematics_enabled=True, tutorial_hints=True, reduced_motion=True)
    (sandbox/'saves/settings.json').write_text(json.dumps(settings))
    protected = [Path(menus.SETTINGS_PATH), Path(menus.CAMPAIGN_PATH), Path(menus.BALANCE_PATH)]
    def user_hashes():
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in protected}
    original_hashes = user_hashes()
    ns: dict[str, Any] = dict(__name__='__native_mission_game_probe__', __file__=str(ROOT/'main.py'))
    original_mode, original_flip = pygame.display.set_mode, pygame.display.flip
    pending = []
    images = []
    receipts = []
    def hidden(size, flags=0, *a, **kw):
        return original_mode(size, (flags & ~pygame.FULLSCREEN)|pygame.HIDDEN, *a, **kw)
    def flip():
        if pending:
            GL.glFinish()
            w,h=pygame.display.get_surface().get_size()
            data=GL.glReadPixels(0,0,w,h,GL.GL_RGB,GL.GL_UNSIGNED_BYTE)
            name=pending.pop(0)
            Image.frombytes('RGB',(w,h),data).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(out/name)
            images.append(name)
        return original_flip()
    with ExitStack() as stack:
        for key,value in dict(USER_DIR=sandbox,SAVES_DIR=sandbox/'saves',
                SETTINGS_PATH=sandbox/'saves/settings.json',CAMPAIGN_PATH=sandbox/'saves/campaign.json',
                BALANCE_PATH=sandbox/'saves/balance.json').items():
            stack.enter_context(patch.object(menus,key,str(value)))
        stack.enter_context(patch.object(pygame.display,'set_mode',hidden))
        stack.enter_context(patch.object(pygame.display,'flip',flip))
        stack.enter_context(patch.object(sys,'argv',[str(ROOT/'main.py'),'--skirmish']))
        try:
            tree=ast.parse((ROOT/'main.py').read_text())
            index=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.While))
            exec(compile(ast.Module(body=tree.body[:index],type_ignores=[]),'main.py','exec'),ns)
            once=ast.For(target=ast.Name(id='_mission_frame',ctx=ast.Store()),
                         iter=ast.Tuple(elts=[ast.Constant(0)],ctx=ast.Load()),body=tree.body[index].body,orelse=[])
            code=compile(ast.fix_missing_locations(ast.Module(body=[once],type_ignores=[])),'main.py','exec')
            def frame(name=None):
                if name: pending.append(name)
                exec(code,ns)
                assert not ns['CPP'].get('failed'), 'Native campaign renderer failed'
                if name: assert not pending, 'Requested actual framebuffer was not captured'
            frame()
            mission=next(m for m in ns['menu'].campaign['missions'] if m['id']=='m00_recovery_drill')
            ns['start_game'](mdef=mission)
            from render import asset_selection
            catalogue=asset_selection.diagnostics()
            assert catalogue['mode']=='preview'
            assert catalogue['pack_order'] and all(p['accepted'] for p in catalogue['pack_order']), catalogue
            assert ns['cinematic'] is not None
            frame('briefing-native.png')
            hud=ns['hud']
            assert hud.native_panels and hud.native_application_model is not None
            assert ns['CPP']['window'].embedded
            receipts.append(dict(phase='briefing',native_application_ops=len(hud.native_application_model['ops'])))
            # Before control: the unchanged historical raster compose, same mission/world/camera.
            saved_native=hud.native_panels
            # Select only the briefing boundary, never demigrate the approved side panels.
            overlay_fn=ns['cpp_overlay_layers']
            def raster_briefing():
                hud.native_application_model=None
                return [ns['cinematic'].compose(*ns['CPP_HUD_SIZE'])]
            ns['cpp_overlay_layers']=raster_briefing
            frame('briefing-before-raster.png')
            ns['cpp_overlay_layers']=overlay_fn
            frame('briefing-native-restored.png')
            assert hud.native_panels is saved_native
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN,mod=0))
            frame()
            pygame.event.post(pygame.event.Event(pygame.KEYUP,key=pygame.K_RETURN,mod=0))
            frame()
            assert ns['cinematic'] is None
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_p,mod=0))
            frame()
            pygame.event.post(pygame.event.Event(pygame.KEYUP,key=pygame.K_p,mod=0))
            frame()
            assert ns['paused']
            stable=state_checksum(ns['state'])
            frame('mission-expanded.png')
            assert hud.mission_hints and not ns['presentation'].panel_rects
            def labels():
                return [op['text'] for op in hud.native_vector_model()['ops'] if op['kind']=='text']
            expanded=labels()
            assert any('Goal:' in s for s in expanded)
            def click_mission():
                button=next(b for b in hud.buttons if b['kind']=='hud_panel' and b['payload']['panel']=='mission')
                r=button['rect']
                pos=(round(r.centerx*args.width/1280),round(r.centery*args.height/800))
                for kind in (pygame.MOUSEBUTTONDOWN,pygame.MOUSEBUTTONUP):
                    pygame.event.post(pygame.event.Event(kind,button=1,pos=pos))
                    frame()
            click_mission()
            assert hud.minimized['mission']
            frame('mission-collapsed.png')
            collapsed=labels()
            assert not any('Goal:' in s or 'Recovery Drill' in s for s in collapsed)
            assert not ns['presentation'].panel_rects
            assert not any(r.collidepoint((640,200)) for r in hud.blocked_rects)
            click_mission()
            frame('mission-restored.png')
            assert not hud.minimized['mission'] and labels()==expanded
            assert state_checksum(ns['state'])==stable
            receipts.append(dict(phase='mission',single_native_panel=True,collapse_hides_hints=True,
                                 restores_content=True,simulation_unchanged=True))
            for language in ('pl','de','ru'):
                from render import i18n
                i18n.set_language(language)
                frame('mission-'+language+'.png')
            i18n.set_language('en')
            sources=['main.py','render/hud.py','render/presentation.py','render/cinematics.py','render/mission_briefing.py','tools/render/capture_native_mission_game.py']
            report=dict(passed=True,entrypoint='main.py stock m00_recovery_drill',drawable=[args.width,args.height],
                        cases=receipts,files=images,catalogue_mode=catalogue['mode'],
                        accepted_visual_packs=len(catalogue['pack_order']),
                        viewer_sha256=hashlib.sha256((ROOT/'render_cpp/build-w02/armada_viewer').read_bytes()).hexdigest(),
                        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                        sources={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
                        library_sha256=hashlib.sha256((ROOT/'render_cpp/build-w02/libarmada_embedded.dylib').read_bytes()).hexdigest())
            (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report))
        finally:
            if 'cpp_reset' in ns: ns['cpp_reset']()
            if ns.get('audio') is not None: ns['audio'].cleanup()
            for key in ('hud','menu','renderer','presentation'):
                obj=ns.get(key)
                if obj is not None and hasattr(obj,'close'): obj.close()
                elif obj is not None and hasattr(obj,'cleanup'): obj.cleanup()
            pygame.quit()
            assert user_hashes()==original_hashes, 'Capture modified owner persistence'


if __name__=='__main__':
    main()
