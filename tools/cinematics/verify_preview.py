"""Bounded real-main look-development capture. Never replaces the shipped movie.

--movie may select a review-only still/sequence ZIP outside assets. This is an
actual startup compositor screenshot, not evidence of a completed animation.
All settings/saves/rings live under --out; invoke under an external timeout.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import runpy
import sys
import time

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--movie',type=Path)
    args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(ROOT));os.chdir(ROOT)
    os.environ['SDL_AUDIODRIVER']='dummy'
    if sys.platform=='darwin':os.environ['SDL_VIDEODRIVER']='cocoa'
    import game.core
    from render import menus,menu_movie
    import pygame
    if args.movie:
        movie=args.movie.resolve(strict=True)
        original_init=menu_movie.MenuMovie.__init__
        def init(self,asset_root,relative_path='menu/battle.zip'):
            original_init(self,movie.parent,movie.name)
        menu_movie.MenuMovie.__init__=init
    user=out/'user';user.mkdir(exist_ok=True)
    settings=user/'settings.json'
    settings.write_text(json.dumps(dict(resolution='2560x1440',fullscreen=False,
        cinematics_enabled=True,reduced_motion=True,language='en',music_volume=0,sfx_volume=0)),encoding='utf-8')
    for key,path in {'USER_DIR':user,'SAVES_DIR':user/'saves','SETTINGS_PATH':settings,
                     'CAMPAIGN_PATH':user/'campaign.json','BALANCE_PATH':user/'balance.json'}.items():
        setattr(menus,key,str(path))
    real_get=pygame.event.get;real_flip=pygame.display.flip
    state={'ns':None,'frames':0,'captured':False};started=time.monotonic()
    def events(*a,**kw):
        state['ns']=sys._getframe(1).f_globals
        if time.monotonic()-started>35:raise AssertionError('Look-development capture inner deadline')
        items=real_get(*a,**kw)
        if state['captured']:items.append(pygame.event.Event(pygame.QUIT))
        return items
    def flip():
        ns=state['ns']
        if ns and ns.get('mode')=='menu' and ns['menu'].screen=='splash':
            state['frames']+=1
            if state['frames']==3:
                from OpenGL.GL import glFinish,glReadPixels,glGetIntegerv,GL_VIEWPORT,GL_RGB,GL_UNSIGNED_BYTE
                glFinish();size=pygame.display.get_surface().get_size()
                assert size==(2560,1440),size
                assert (ns['menu'].width,ns['menu'].height)==size
                assert ns['menu']._surface.get_size()==size
                assert tuple(glGetIntegerv(GL_VIEWPORT))[2:]==size
                movie=ns['menu']._menu_movie
                assert movie.available
                pixels=bytes(glReadPixels(0,0,*size,GL_RGB,GL_UNSIGNED_BYTE))
                surface=pygame.image.frombytes(pixels,size,'RGB')
                surface=pygame.transform.flip(surface,False,True)
                image=out/'splash.png';pygame.image.save(surface,str(image))
                receipt=dict(scope='real main startup compositor; frozen look-development frame, not completed animation',
                    actual_size=size,movie_metadata=movie.metadata,
                    screenshot_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                    movie_sha256=hashlib.sha256(Path(movie._zip.filename).read_bytes()).hexdigest(),
                    frame_surface_size=list(ns['menu']._surface.get_size()))
                (out/'capture.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
                state['captured']=True
        real_flip()
    pygame.event.get=events;pygame.display.flip=flip
    sys.argv=[str(ROOT/'main.py')]
    runpy.run_path(str(ROOT/'main.py'),run_name='__main__')
    assert state['captured'],'Main did not reach actual splash compositor'
    print('CINEMATIC_COMPOSITOR_OK',out/'splash.png')


if __name__=='__main__':
    main()
