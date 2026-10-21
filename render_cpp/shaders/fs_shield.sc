// W05 slice 5: the shell carries its own baked light; additive blending does the rest.
$input v_colour
#include <bgfx_shader.sh>

void main()
{
    gl_FragColor = v_colour;
}
