$input v_texcoord0, v_color0

#include <bgfx_shader.sh>

SAMPLER2D(s_top_hud, 0);

// White RGB / coverage alpha atlas; straight-alpha UI colours, no world lighting.
void main() {
    gl_FragColor = v_color0 * texture2D(s_top_hud, v_texcoord0);
}
