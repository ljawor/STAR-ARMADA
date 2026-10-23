"""Real SDL/GL deployment capture, input and layout acceptance; isolated user data."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    processes = subprocess.check_output(['ps','-axo','pid=,args='], text=True)
    for row in processes.splitlines():
        parts = row.split()
        if any(Path(token).name == 'main.py' for token in parts[2:]) and '-c' not in parts:
            raise SystemExit('Close the running game before this GPU diagnostic: ' + row)
    import pygame
    import numpy as np
    from OpenGL.GL import glViewport, glReadPixels, glGetError, glClear, glFinish, GL_RGB, GL_UNSIGNED_BYTE, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT
    from render import menus
    from game.core.skirmish import SKIRMISH_MAP_IDS, PLAYER_COLORS, build_skirmish_map
    from game.core.manager import GameManager
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    pygame.init()
    try:
        with ExitStack() as stack:
            root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            for name,leaf in [('USER_DIR',''),('SAVES_DIR','saves'),('SETTINGS_PATH','settings.json'),('CAMPAIGN_PATH','campaign.json'),('BALANCE_PATH','balance.json')]:
                stack.enter_context(patch.object(menus,name,str(root/leaf)))
            def press(menu,action,payload=None):
                b = next(b for b in menu.buttons if b['action']==action and (payload is None or b['payload']==payload))
                for kind in (pygame.MOUSEBUTTONDOWN,pygame.MOUSEBUTTONUP):
                    menu.handle_event(pygame.event.Event(kind,pos=b['rect'].center,button=1))
            for width,height in [(800,600),(1024,768),(1440,900)]:
                pygame.display.set_mode((width,height),pygame.DOUBLEBUF|pygame.OPENGL)
                glViewport(0,0,width,height)
                for mid in SKIRMISH_MAP_IDS:
                    menu = menus.MenuStack(width,height)
                    try:
                        menu.screen='skirmish'
                        menu.render(0)
                        press(menu,'skirmish_map',mid)
                        menu.render(0)
                        capacity=menu.skirmish_capacity(mid)
                        while menu.skirmish_options['ai_count'] < capacity-1:
                            press(menu,'skirmish_ai',1)
                            menu.render(0)
                        press(menu,'skirmish_spawn_point',capacity-1)
                        menu.render(0)
                        window=pygame.Rect(0,0,width,height)
                        for i,b in enumerate(menu.buttons):
                            assert window.contains(b['rect']),b
                            assert not any(b['rect'].colliderect(v['rect']) for v in menu.buttons[i+1:]),b
                        for i,r in enumerate(menu.skirmish_text_bounds):
                            assert window.contains(r),r
                            assert not any(r.colliderect(v) for v in menu.skirmish_text_bounds[i+1:]),r
                        glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
                        menu.draw_gl()
                        glFinish()
                        frame=np.flipud(np.frombuffer(glReadPixels(0,0,width,height,GL_RGB,GL_UNSIGNED_BYTE),dtype=np.uint8).reshape(height,width,3)).copy()
                        assert glGetError()==0
                        for anchor,(x,y) in enumerate(menu.skirmish_preview_starts):
                            owner=menu.skirmish_options['spawn_slots'].index(anchor)
                            expected=np.array([round(v*255) for v in PLAYER_COLORS[menu.skirmish_options['colors'][owner]]])
                            assert np.max(np.abs(frame[y,x].astype(int)-expected))<=8,(mid,anchor,frame[y,x],expected)
                        path=out/f'{width}x{height}_{mid}_{capacity}players.png'
                        pygame.image.save(pygame.image.frombuffer(frame.tobytes(),(width,height),'RGB'),str(path))
                        press(menu,'launch_skirmish')
                        assert menu.result==menus.MenuResult.START_SKIRMISH
                        built=build_skirmish_map(menu.skirmish_store,menu.result_payload)
                        assert built['players'][0]['start']==menu.skirmish_store.maps[mid]['players'][-1]['start']
                        gm=GameManager.start_skirmish(built)
                        assert len(gm.state.players)==capacity
                        for _ in range(3): gm.step(1/30)
                        assert not gm.state.game_over
                        rows.append(dict(map=mid,size=[width,height],players=capacity,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),capture=path.name))
                        print('PASS',width,height,mid,capacity,flush=True)
                    finally:
                        menu.close()
            report=dict(captures=rows,count=len(rows),scope='Real SDL/OpenGL menu, full-capacity input/layout/color pixels and backend launch. Not native Windows or interactive performance acceptance.')
            (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            assert len(rows)==24
            print('SKIRMISH_MENU_DIAG_OK',len(rows))
    finally:
        pygame.quit()

if __name__=='__main__':
    main()
