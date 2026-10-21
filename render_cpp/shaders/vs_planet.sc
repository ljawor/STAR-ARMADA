$input a_position, a_normal, a_texcoord0
$output v_world, v_normal, v_texcoord0
#include <bgfx_shader.sh>
// The body matrix is a plain uniform, set per submit.
uniform mat4 u_planet_model;
void main() {
    mat4 model = u_planet_model;
    vec4 world = mul(model, vec4(a_position, 1.0));
    gl_Position = mul(u_viewProj, world);
    v_world = world.xyz;
    v_normal = normalize(mul(model, vec4(a_normal, 0.0)).xyz);
    v_texcoord0 = a_texcoord0;
}
