"""S07 offline cinematic selected/legacy real-renderer evidence; not campaign acceptance."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path('/Users/lukaszjawor/.hermes/cache/scratch/star-armada-s07-integration')
sys.path.insert(0,str(ROOT)); os.chdir(ROOT)
import pygame,numpy as np
from OpenGL import GL
from tools.build_menu_movie import PresentationFixture,camera_pose
from render import asset_selection
from render.camera import Camera
from render.renderer import Renderer
from game.benchmark import state_hash
out=ROOT/'artifacts/s07-runtime-acceptance/cinematic-attempt1'
out.mkdir(parents=True,exist_ok=False)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
protected=json.loads((ROOT/'artifacts/s07-integration/S07-PROTECTED-INPUTS.json').read_text())['sha256']
report={'scope':'Offline synthetic presentation through production renderer, explicit legacy/preview configuration. Not a candidate movie ZIP, campaign launch, FPS, or full S07 acceptance.', 'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'probe_sha256':sha(__file__),'variants':{},'comparisons':{}}
pygame.display.init()
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1)
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4)
pygame.display.set_mode((1280,720),pygame.OPENGL|pygame.DOUBLEBUF)
GL.glViewport(0,0,1280,720)
report['gl']={k:GL.glGetString(v).decode() for k,v in [('vendor',GL.GL_VENDOR),('renderer',GL.GL_RENDERER),('version',GL.GL_VERSION)]}
report['samples']=int(GL.glGetIntegerv(GL.GL_SAMPLES)); assert report['samples']==4
assert not os.environ.get('STAR_ARMADA_FIXED_MATERIALS')
r=None; captures={}
try:
    for preview in (False,True):
        mode='preview' if preview else 'legacy'
        asset_selection.configure({'model_preview':preview},asset_root=ROOT)
        fixture=PresentationFixture(); st=fixture.state
        cam=Camera(1280,720); cam.target=[0.,15.,0.]
        r=Renderer(st,cam); r.marker_mode='off'; r.diff_render=True
        assert not r.skip and r.materials.available
        pins=[]
        for e in st.entities.values():
            binding=asset_selection.ship_binding(fixture.ds,e.data_id,st.players[e.owner].faction)
            resolved=asset_selection._resolver.resolve(binding) if binding else None
            pins.append({'data_id':e.data_id,'owner':e.owner,'binding':binding,'revision':resolved.revision if resolved else None})
        if preview: assert all(p['revision'] for p in pins)
        result={'selection':asset_selection.diagnostics(),'models':pins,'frames':[]}; report['variants'][mode]=result
        for name,t in [('start',1.),('middle',8.5),('end',15.9583333333)]:
            fixture.sample(t); cam.yaw,cam.pitch,cam.distance=camera_pose(t); r.time=t
            before=state_hash(st)
            def draw():
                pygame.event.pump(); r.draw(0.,set()); GL.glFinish()
                assert GL.glGetError()==GL.GL_NO_ERROR
                assert state_hash(st)==before
                return np.frombuffer(GL.glReadPixels(0,0,1280,720,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(720,1280,3)[::-1].copy()
            for _ in range(3): draw()
            image=draw(); repeated=draw(); changed=int(np.any(image!=repeated,axis=2).sum())
            assert changed==0,(mode,name,changed)
            centers=[cam.world_to_screen(e.pos.x,e.pos.y,e.pos.z) for e in st.entities.values()]
            assert all(p is not None and 0<=p[0]<1280 and 0<=p[1]<720 for p in centers)
            path=out/f'{mode}-{name}.png'
            pygame.image.save(pygame.image.frombuffer(image.tobytes(),(1280,720),'RGB'),path)
            result['frames'].append({'file':path.name,'sha256':sha(path),'time':t,'state_sha256':before,'repeat_changed_pixels':changed,'visible_centers':len(centers)})
            captures[mode,name]=image
        if preview:
            ffmpeg=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size','1280x720','-framerate','24','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',str(out/'candidate-motion.mp4')],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
            for i in range(48):
                fixture.sample(1+i/24); cam.yaw,cam.pitch,cam.distance=camera_pose(1+i/24); r.time=1+i/24
                before=state_hash(st); ffmpeg.stdin.write(draw().tobytes())
            ffmpeg.stdin.close(); err=ffmpeg.stderr.read(); assert ffmpeg.wait()==0,err
            report['motion']={'file':'candidate-motion.mp4','frames':48,'fps':24,'sha256':sha(out/'candidate-motion.mp4'),'scope':'2-second offline synthetic fixture; rendering preserves each sampled state'}
        r.close(); r=None
    for name in ('start','middle','end'):
        count=int(np.any(captures['legacy',name]!=captures['preview',name],axis=2).sum()); assert count>0
        report['comparisons'][name]={'changed_pixels':count}
    sheet=pygame.Surface((1280,780)); sheet.fill((12,17,25)); pygame.font.init(); font=pygame.font.SysFont('Arial',20)
    for col,mode in enumerate(('legacy','preview')):
        for row,name in enumerate(('start','middle','end')):
            tile=pygame.image.frombuffer(captures[mode,name].tobytes(),(1280,720),'RGB')
            sheet.blit(pygame.transform.smoothscale(tile,(640,230)),(col*640,row*260+30))
            sheet.blit(font.render(f'{mode.upper()} | {name}',True,(240,240,245)),(col*640+12,row*260+5))
    pygame.image.save(sheet,out/'comparison.jpg')
finally:
    if r: r.close()
    asset_selection.configure({}); pygame.quit()
    report['protected_inputs_changed']=[p for p,h in protected.items() if sha(ROOT/p)!=h]
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
assert not report['protected_inputs_changed']
print(json.dumps(report,indent=2))
