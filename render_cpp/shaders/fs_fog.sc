$input v_texcoord0
#include <bgfx_shader.sh>
SAMPLER2D(s_fog, 0);
// The mask carries its own colour and alpha: (12,22,38,155) charted but unseen, (3,6,13,255)
// unexplored, alpha 0 where the team's sensors reach. Nearest filtering, because the Python
// renderer draws the same cells as hard edges - a smoothed mask would invent a visibility gradient
// the simulation does not have.
void main() {
    gl_FragColor = texture2D(s_fog, v_texcoord0);
}
