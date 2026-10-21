// W05 slice 5: one instanced shield shell.
//
// The mesh is a unit hemisphere built in VIEW space, so it always faces the eye and the baked
// latitude terms (whiten, alpha) stay valid for every shell at every heading - the same trick that
// lets the Python renderer cache one display list per strength octant. Each instance supplies its
// view-space centre and radius, and the tint/fade the simulation decided.
//
// u_proj is a bgfx built-in uniform (bgfx_shader.sh), so no uniform is created for it.
$input a_position, a_texcoord0, i_data0, i_data1
$output v_colour
#include <bgfx_shader.sh>

void main()
{
    // i_data0 = (view-space centre, radius); i_data1 = (tint rgb, fade)
    vec4 view = vec4(a_position * i_data0.w + i_data0.xyz, 1.0);
    gl_Position = mul(u_proj, view);
    // The limb is pulled toward white by a capped term; the body keeps the strength hue.
    vec3 rgb = mix(i_data1.rgb, vec3(1.0, 1.0, 1.0), clamp(a_texcoord0.x, 0.0, 1.0));
    v_colour = vec4(rgb, clamp(a_texcoord0.y * i_data1.a, 0.0, 1.0));
}
