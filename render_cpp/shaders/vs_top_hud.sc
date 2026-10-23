$input a_position, a_texcoord0, a_color0
$output v_texcoord0, v_color0

#include <bgfx_shader.sh>

// Positions are measured in the actual framebuffer, then converted to clip space.
void main() {
    gl_Position = vec4(a_position.xy, 0.0, 1.0);
    v_texcoord0 = a_texcoord0;
    v_color0 = a_color0;
}
