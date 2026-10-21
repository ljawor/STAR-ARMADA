$input a_position, a_normal, a_color0, a_color1, i_data0, i_data1, i_data2, i_data3, i_data4
$output v_world, v_normal, v_color0, v_shadow
#include <bgfx_shader.sh>
uniform mat4 u_lightMatrix;
void main() {
    mat4 model=mtxFromCols(i_data0,i_data1,i_data2,i_data3);
    vec4 world=mul(model,vec4(a_position,1.0));
    gl_Position=mul(u_viewProj,world);
    v_world=world.xyz;
    v_normal=normalize(mul(model,vec4(a_normal,0.0)).xyz);
    v_color0=vec4(mix(a_color0.rgb,i_data4.rgb,a_color1.x),a_color0.a);
    v_shadow=mul(u_lightMatrix,world);
}
