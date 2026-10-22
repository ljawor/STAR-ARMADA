$input v_texcoord0, v_color0

#include <bgfx_shader.sh>

void main()
{
    // Compact radial C1 falloff: exactly zero at/outside the unit disc, including
    // every quad corner. Straight RGB, not premultiplied: parent blends SRC_ALPHA,
    // ONE (BLEND_ADD would ignore this falloff and recreate the square confetti).
    float falloff = max(0.0, 1.0 - dot(v_texcoord0, v_texcoord0));
    gl_FragColor = vec4(v_color0.rgb, v_color0.a * falloff * falloff);
}
