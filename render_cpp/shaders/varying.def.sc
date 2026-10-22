vec3 a_position : POSITION;
vec2 a_texcoord0 : TEXCOORD0;
vec3 a_normal : NORMAL;
vec4 a_color0 : COLOR0;
vec4 a_color1 : COLOR1;
vec4 i_data0 : TEXCOORD7;
vec4 i_data1 : TEXCOORD6;
vec4 i_data2 : TEXCOORD5;
vec4 i_data3 : TEXCOORD4;
vec4 i_data4 : TEXCOORD3;
vec3 v_world : TEXCOORD0;
vec3 v_normal : TEXCOORD1;
vec4 v_color0 : COLOR0;
vec4 v_shadow : TEXCOORD2;
// Per-instance coverage: the placement preview is one instance with alpha < 1, so the
// translucency rides the instance stream instead of a per-draw uniform.
float v_alpha : TEXCOORD4;
vec2 v_texcoord0 : TEXCOORD3;
// W05 slice 5: the shell's own colour (tint pulled toward white, alpha after fade). TEXCOORD5 and 6
// are free because the instanced pass declares only i_data0/i_data1.
vec4 v_colour : TEXCOORD5;
