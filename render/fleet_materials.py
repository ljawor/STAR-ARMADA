"""GLSL 1.20 compatibility materials over the existing solid display-list meshes.

Only opaque hull/planet passes use programs. Effects, shields and HUD retain the
fixed pipeline. Program scopes restore their caller and failed compilation falls
back to fixed lighting (with a warning). Requires a current, real GL context.
"""
from __future__ import annotations
from contextlib import contextmanager
import logging
import os
from OpenGL import GL

VERTEX = """#version 120
varying vec3 eyePos, eyeNormal, modelPos, modelNormal;
varying vec4 color;
varying vec2 uv;
void main() {
    eyePos = (gl_ModelViewMatrix * gl_Vertex).xyz;
    eyeNormal = normalize(gl_NormalMatrix * gl_Normal);
    modelPos = gl_Vertex.xyz;
    modelNormal = gl_Normal;
    uv = gl_MultiTexCoord0.xy;
    color = gl_Color;
    gl_Position = ftransform();
}
"""

HULL = """#version 120
varying vec3 eyePos, eyeNormal, modelPos, modelNormal;
varying vec4 color;
varying vec2 uv;
uniform float materialPass;
// Only the Blender-authored Alliance battleship opts into this treatment.
uniform float authoredSurface;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
void main() {
    vec3 N = normalize(eyeNormal);
    if (!gl_FrontFacing) N = -N;
    vec3 V = normalize(-eyePos);
    vec3 L = normalize(gl_LightSource[0].position.xyz - eyePos);
    vec3 H = normalize(L+V);
    vec3 an = abs(modelNormal);
    vec2 p = modelPos.xz;
    if (an.x > an.y && an.x > an.z) p = modelPos.zy;
    else if (an.z > an.y) p = modelPos.xy;
    // Staggered plates: screen derivative widens seams only when resolvable.
    vec2 q = p / vec2(5.5, 9.0);
    q.x += mod(floor(q.y), 2.0) * .5;
    vec2 cell = floor(q);
    vec2 f = fract(q);
    vec2 fw = max(fwidth(q), vec2(.003));
    vec2 edge = min(f, 1.0-f);
    vec2 lines = 1.0-smoothstep(vec2(.016), vec2(.016)+fw, edge);
    float resolve = 1.0-smoothstep(.12,.45,max(fw.x,fw.y));
    float seam = max(lines.x,lines.y)*resolve;
    float panel = hash(cell);
    float hatch = step(.80, panel) * (1.0-smoothstep(.27,.32,abs(f.x-.5)))
                   * (1.0-smoothstep(.29,.34,abs(f.y-.5))) * resolve;
    float louvers = (1.0-smoothstep(.23,.36,abs(fract(f.y*9.0)-.5))) * hatch;
    float bevel = (1.0-smoothstep(.027,.027+fw.y,edge.y))*resolve;
    // Bare titanium with broad faction-painted stripes, not an all-over toy tint.
    float stripe = (1.0-smoothstep(1.4,2.0,abs(abs(modelPos.x)-10.0)));
    stripe = max(stripe, (1.0-smoothstep(2.2,2.6,abs(modelPos.z-24.0)))*.75);
    vec3 alloy = mix(vec3(.39,.44,.50), color.rgb, .20);
    alloy = mix(alloy, color.rgb * .92, stripe * .87);
    if (materialPass > .5 && materialPass < 1.5) alloy *= .51;
    if (materialPass > 1.5) alloy = mix(vec3(.63,.68,.72),color.rgb,.28);
    alloy *= .84 + .24 * panel;
    alloy *= 1.0 - .43 * seam - .30 * hatch - .20 * louvers;
    alloy += vec3(.055) * bevel * (1.0-seam);
    if (authoredSurface > .5) {
        // Geometry supplies armor seams, bevels and vents on the authored hull.
        // Sparse low-contrast plate variation must not repaint them as hatching.
        vec2 aq = p / vec2(22.0,32.0);
        vec2 af = fract(aq);
        vec2 aw = max(fwidth(aq),vec2(.001));
        vec2 ae = min(af,1.0-af);
        vec2 al = 1.0-smoothstep(vec2(.004),vec2(.004)+aw,ae);
        seam = max(al.x,al.y)*(1.0-smoothstep(.12,.45,max(aw.x,aw.y)));
        panel = hash(floor(aq));
        alloy = mix(vec3(.43,.47,.52),color.rgb,.10);
        if (materialPass > .5 && materialPass < 1.5)
            alloy = mix(vec3(.055,.073,.095),color.rgb*.16,.18);
        if (materialPass > 1.5)
            alloy = mix(vec3(.55,.60,.65),color.rgb,.14);
        alloy *= (.98+.04*panel)*(1.0-.12*seam);
    }
    float ndl = max(dot(N,L), 0.0);
    float fresnel = pow(1.0-max(dot(N,V),0.0),4.0);
    float roughness = mix(48.0,18.0,panel);
    float spec = pow(max(dot(N,H),0.0),roughness) * ndl;
    vec3 ambient = vec3(.20,.26,.36) + vec3(.08,.10,.14)*max(N.y,0.0);
    vec3 result = alloy*(ambient+vec3(1.0,.92,.80)*ndl*.92);
    float polish = authoredSurface > .5 ? .24 : .62;
    if (authoredSurface > .5 && materialPass > .5 && materialPass < 1.5) polish = .08;
    result += vec3(.72,.81,.96)*spec*polish*(1.0-seam*.8);
    result += vec3(.15,.23,.34)*fresnel*.32;
    // Mild display transfer: preserve black recesses, expose neutral armor.
    result = pow(max(result,vec3(0.0)),vec3(.84));
    gl_FragColor = vec4(result, color.a);
}
"""

PLANET = """#version 120
varying vec3 eyePos, eyeNormal, modelPos, modelNormal;
varying vec4 color;
varying vec2 uv;
uniform sampler2D surfaceMap;
uniform float atmosphere;
uniform float shell;
void main() {
    vec3 N = normalize(eyeNormal);
    vec3 V = normalize(-eyePos);
    vec3 L = normalize(gl_LightSource[0].position.xyz-eyePos);
    float day = dot(N,L);
    float rim = pow(1.0-max(dot(N,V),0.0),3.8);
    vec3 air = vec3(.19,.48,1.0);
    if (shell > .5) {
        float alpha = rim * (.09+.37*smoothstep(-.35,.6,day)) * atmosphere;
        gl_FragColor = vec4(air,alpha);
    } else {
        vec3 albedo = texture2D(surfaceMap,uv).rgb;
        float diffuse = smoothstep(-.10,.85,day);
        vec3 result = albedo * (vec3(.025,.035,.065) + vec3(.98,.94,.87)*diffuse);
        float ocean = smoothstep(.02,.12,albedo.b-albedo.r);
        float spec = pow(max(dot(N,normalize(L+V)),0.0),70.0);
        result += vec3(.6,.72,.8)*spec*ocean*diffuse*.5;
        result += air * rim * atmosphere * (.12+.30*diffuse);
        gl_FragColor = vec4(pow(max(result,vec3(0.0)),vec3(.88)),1.0);
    }
}
"""


class FleetMaterials:
    def __init__(self):
        self.programs = {}
        self.locations = {}
        self.error = None
        if os.environ.get('STAR_ARMADA_FIXED_MATERIALS') == '1':
            return
        try:
            for name, frag in (('hull', HULL), ('planet', PLANET)):
                stages = []
                attached = []
                program = None
                try:
                    for source, kind in ((VERTEX, GL.GL_VERTEX_SHADER),
                                         (frag, GL.GL_FRAGMENT_SHADER)):
                        shader = GL.glCreateShader(kind)
                        if not shader:
                            raise RuntimeError('Could not allocate fleet shader')
                        stages.append(shader)  # own it before any fallible call
                        GL.glShaderSource(shader, source)
                        GL.glCompileShader(shader)
                        if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
                            raise RuntimeError(GL.glGetShaderInfoLog(shader))
                    program = GL.glCreateProgram()
                    if not program:
                        raise RuntimeError('Could not allocate fleet program')
                    for shader in stages:
                        GL.glAttachShader(program, shader)
                        attached.append(shader)
                    GL.glLinkProgram(program)
                    if not GL.glGetProgramiv(program, GL.GL_LINK_STATUS):
                        raise RuntimeError(GL.glGetProgramInfoLog(program))
                    self.programs[name] = program
                finally:
                    for shader in attached:
                        GL.glDetachShader(program, shader)
                    for shader in stages:
                        GL.glDeleteShader(shader)
                    if program and name not in self.programs:
                        GL.glDeleteProgram(program)
            for name, program in self.programs.items():
                for uniform in ('materialPass', 'authoredSurface', 'surfaceMap', 'atmosphere', 'shell'):
                    self.locations[name, uniform] = GL.glGetUniformLocation(program, uniform)
        except Exception as exc:
            self.error = str(exc)
            logging.getLogger(__name__).warning('Fleet GLSL unavailable; using fixed lighting: %s', exc)
            self.close()

    @property
    def available(self):
        return bool(self.programs)

    @contextmanager
    def use(self, name, **uniforms):
        if name not in self.programs:
            yield
            return
        previous = int(GL.glGetIntegerv(GL.GL_CURRENT_PROGRAM))
        GL.glUseProgram(self.programs[name])
        try:
            if name == 'planet':
                GL.glUniform1i(self.locations[name, 'surfaceMap'], 0)
            elif name == 'hull':
                GL.glUniform1f(self.locations[name, 'authoredSurface'], 0.)
            for key, value in uniforms.items():
                GL.glUniform1f(self.locations[name, key], value)
            yield
        finally:
            GL.glUseProgram(previous)

    def hull_pass(self, value, authored=False):
        """No-op if no program is active; only safe inside `use('hull', ...)` scope."""
        if self.available and 'hull' in self.programs:
            program = int(GL.glGetIntegerv(GL.GL_CURRENT_PROGRAM))
            if program == self.programs['hull']:
                GL.glUniform1f(self.locations['hull', 'materialPass'], value)
                GL.glUniform1f(self.locations['hull', 'authoredSurface'], float(authored))

    def close(self):
        for program in self.programs.values():
            GL.glDeleteProgram(program)
        self.programs.clear()
