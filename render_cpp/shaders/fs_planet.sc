$input v_world, v_normal, v_texcoord0
#include <bgfx_shader.sh>
SAMPLER2D(s_planet, 0);
uniform vec4 u_eye;
uniform vec4 u_star;          // the star this map lights every planet from
uniform vec4 u_planet_flags;  // x: atmosphere (1) or none (0)
//
// A port of render/fleet_materials.py::PLANET, not a re-invention: the same ambient, the same
// smoothstep terminator, the same ocean highlight, the same atmosphere rim and the same display
// transfer. Two renderers that light a planet differently are two different worlds, and W05's
// measure is that a player cannot tell them apart.
float planetSmoothstep(float edge0, float edge1, float x) {
    float t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
}
void main() {
    vec3 N = normalize(v_normal);
    vec3 V = normalize(u_eye.xyz - v_world);
    vec3 L = normalize(u_star.xyz - v_world);
    float day = dot(N, L);
    float rim = pow(1.0 - max(dot(N, V), 0.0), 3.8);
    vec3 air = vec3(0.19, 0.48, 1.0);
    float atmosphere = u_planet_flags.x;
    vec3 albedo = texture2D(s_planet, v_texcoord0).rgb;
    float diffuse = planetSmoothstep(-0.10, 0.85, day);
    vec3 result = albedo * (vec3(0.025, 0.035, 0.065) + vec3(0.98, 0.94, 0.87) * diffuse);
    float ocean = planetSmoothstep(0.02, 0.12, albedo.b - albedo.r);
    float spec = pow(max(dot(N, normalize(L + V)), 0.0), 70.0);
    result += vec3(0.6, 0.72, 0.8) * spec * ocean * diffuse * 0.5;
    result += air * rim * atmosphere * (0.12 + 0.30 * diffuse);
    gl_FragColor = vec4(pow(max(result, vec3(0.0,0.0,0.0)), vec3(0.88,0.88,0.88)), 1.0);
}
