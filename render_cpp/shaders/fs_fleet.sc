$input v_world, v_normal, v_color0, v_shadow
#include <bgfx_shader.sh>
SAMPLER2DSHADOW(s_shadow,0);
uniform vec4 u_eye;
uniform vec4 u_options;
float visibility(vec4 shadowPosition) {
    if(u_options.x<0.5) return 1.0;
    vec3 p=shadowPosition.xyz/shadowPosition.w;
    if(any(lessThan(p,vec3(0.0))) || any(greaterThan(p,vec3(1.0)))) return 1.0;
    float s=0.0;
    for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++)
        s+=shadow2D(s_shadow,vec3(p.xy+vec2(float(x),float(y))/2048.0,p.z-0.0008));
    return s/9.0;
}
void main() {
    vec3 N=normalize(v_normal);
    vec3 V=normalize(u_eye.xyz-v_world);
    if(dot(N,V)<0.0) N=-N;
    vec3 L=normalize(vec3(-0.45,0.8,0.4));
    vec3 H=normalize(L+V);
    float nl=max(dot(N,L),0.0),nv=max(dot(N,V),0.001),nh=max(dot(N,H),0.0),vh=max(dot(V,H),0.0);
    float rough=0.44, a=rough*rough, a2=a*a;
    float den=nh*nh*(a2-1.0)+1.0;
    float D=a2/(3.14159265*den*den+0.0001);
    float k=(rough+1.0)*(rough+1.0)/8.0;
    float G=(nl/(nl*(1.0-k)+k))*(nv/(nv*(1.0-k)+k));
    vec3 base=v_color0.rgb;
    vec3 F0=mix(vec3(0.04),base,0.55);
    vec3 F=F0+(vec3(1.0)-F0)*pow(1.0-vh,5.0);
    vec3 spec=D*G*F/(4.0*max(nl,0.001)*nv+0.0001);
    float sh=visibility(v_shadow);
    vec3 lit=base*(0.17+0.10*max(N.y,0.0))+(base*0.65+spec)*nl*sh*1.55;
    lit+=base*pow(1.0-nv,3.0)*0.13;
    lit=mix(lit,base*2.0,v_color0.a);
    lit=lit/(lit+vec3(1.0));
    gl_FragColor=vec4(pow(lit,vec3(1.0/2.2)),1.0);
}
