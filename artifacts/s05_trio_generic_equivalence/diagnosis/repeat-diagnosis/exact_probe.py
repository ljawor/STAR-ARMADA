import sys, importlib.util, argparse,json
from pathlib import Path
root=Path('/Users/lukaszjawor/.hermes/cache/scratch');repo=root/'star-armada-s05';out=root/'s05-repeat-diagnosis'/'exact1'
spec=importlib.util.spec_from_file_location('harness',repo/'tools/diag_trio_generic_equivalence.py');h=importlib.util.module_from_spec(spec)
text=(repo/'tools/diag_trio_generic_equivalence.py').read_text()
text=text.replace("raise AssertionError(name+': unstable repeated frame')", """diagnosis={'name':name,'readback':pixel_metrics(b,np.frombuffer(GL.glReadPixels(0,0,W,H,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(H,W,3)[::-1].copy()),'repeats':[]}
                previous=b
                for extra in range(30):
                    image=pixels(spec,time)
                    diagnosis['repeats'].append(pixel_metrics(previous,image))
                    save('diagnosis-'+str(extra),image)
                    previous=image
                dump(output/'diagnosis.json',diagnosis)
                raise AssertionError(name+': unstable repeated frame')""")
text=text.replace("report['frames'].append(row)","""report['frames'].append(row)
            if name=='motion-0270-escort-close':
                dump(output/'stopped-at-270.json',{'repeat_stable':True})
                raise SystemExit('diagnostic bounded stop at 270')""")
exec(compile(text,str(repo/'tools/diag_trio_generic_equivalence.py'),'exec'),h.__dict__)
a=argparse.Namespace(source=root/'s05-parent-verification/sources/candidate',output=out,selection='preview',peer=root/'s05-parent-verification/control')
h.child(a)
