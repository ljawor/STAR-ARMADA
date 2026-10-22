$input a_position, a_texcoord0, a_color0, a_color1
$output v_texcoord0, v_color0

#include <bgfx_shader.sh>

// xy = active view framebuffer width/height in pixels; zw reserved, set to 0.
// Radius a_color1.x is in those same pixels (not logical window coordinates).
uniform vec4 u_star_viewport;

void main()
{
    // w=0 preserves all view rotation, including camera inclination, but drops
    // camera translation entirely. Reintroduce w=1 ONLY after that transform.
    vec3 skyView = mul(u_view, vec4(a_position * 90000.0, 0.0)).xyz;
    vec4 clip = mul(u_proj, vec4(skyView, 1.0));
    vec2 viewport = max(u_star_viewport.xy, vec2(1.0, 1.0));
    clip.xy += a_texcoord0 * a_color1.x * (2.0 / viewport) * clip.w;
    // Far depth for both homogeneous [-1,1] and [0,1] projection conventions.
    // Parent MUST use DEPTH_TEST_LEQUAL, no WRITE_Z, same world depth attachment.
    // Do not abs(clip.w): back-hemisphere stars must remain behind the camera.
    clip.z = clip.w;
    gl_Position = clip;
    v_texcoord0 = a_texcoord0;
    v_color0 = a_color0;
}
