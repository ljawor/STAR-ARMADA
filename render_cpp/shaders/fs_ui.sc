$input v_texcoord0

#include <bgfx_shader.sh>

// The HUD arrives as display colours with straight alpha (pygame SRCALPHA surface): no lighting,
// no depth, no gamma. Blending is done by the fixed-function state set at submit time.
SAMPLER2D(s_overlay, 0);

void main() {
    gl_FragColor = texture2D(s_overlay, v_texcoord0);
}
