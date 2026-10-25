cmake_minimum_required(VERSION 3.25)
project(armada_offline_viewer LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
# MSVC hides the classic math constants (M_PI) behind _USE_MATH_DEFINES; viewer.cpp,
# frame_v2.hpp and their tests use them. Harmless on the POSIX toolchains.
add_compile_definitions(_USE_MATH_DEFINES)
include(FetchContent)

# Source pins are deliberate: bgfx's initialization API changes across revisions.
set(ARMADA_BGFX_CMAKE_REV b07783852a1cb0636a07f51a92d5366974579245)
set(ARMADA_BGFX_PREFIX "" CACHE PATH "Optional prebuilt package from the documented exact bgfx pins")
set(ARMADA_SHADERC "" CACHE FILEPATH "Prebuilt shaderc at the same bgfx pin (with ARMADA_BGFX_PREFIX)")
set(ARMADA_BGFX_SHADER_INCLUDE "" CACHE PATH "bgfx src directory containing bgfx_shader.sh")
find_package(SDL3 3.4 CONFIG QUIET)
if(NOT SDL3_FOUND)
  set(SDL_SHARED OFF CACHE BOOL "" FORCE)
  set(SDL_STATIC ON CACHE BOOL "" FORCE)
  set(SDL_TESTS OFF CACHE BOOL "" FORCE)
  FetchContent_Declare(SDL3 GIT_REPOSITORY https://github.com/libsdl-org/SDL.git GIT_TAG release-3.4.14 GIT_SHALLOW TRUE)
  FetchContent_MakeAvailable(SDL3)
endif()
if(ARMADA_BGFX_PREFIX)
  find_package(bgfx CONFIG REQUIRED PATHS "${ARMADA_BGFX_PREFIX}/lib/cmake/bgfx" NO_DEFAULT_PATH)
  if(NOT EXISTS "${ARMADA_SHADERC}" OR NOT EXISTS "${ARMADA_BGFX_SHADER_INCLUDE}/bgfx_shader.sh")
    message(FATAL_ERROR "Prebuilt bgfx needs ARMADA_SHADERC and ARMADA_BGFX_SHADER_INCLUDE from the same pin")
  endif()
  set(ARMADA_BGFX_TARGET bgfx::bgfx)
  # A prebuilt bgfx must be compiled with the same instance-attribute semantics as the fetched
  # build below, or the world pass silently loses every instance transform (see the note there).
  message(STATUS "armada: prebuilt bgfx must define BGFX_CONFIG_INSTANCE_DATA_FIRST_TEXCOORD=7")
  set(SHADERC_COMMAND "${ARMADA_SHADERC}")
  set(SHADERC_DEPENDENCY "${ARMADA_SHADERC}")
else()
  set(BGFX_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
  set(BGFX_BUILD_TESTS OFF CACHE BOOL "" FORCE)
  set(BGFX_BUILD_TOOLS ON CACHE BOOL "" FORCE)
  set(BGFX_BUILD_TOOLS_GEOMETRY OFF CACHE BOOL "" FORCE)
  set(BGFX_BUILD_TOOLS_TEXTURE OFF CACHE BOOL "" FORCE)
  set(BGFX_BUILD_TOOLS_BIN2C OFF CACHE BOOL "" FORCE)
  set(BGFX_BUILD_EXAMPLE_COMMON OFF CACHE BOOL "" FORCE)
  FetchContent_Declare(bgfx_cmake GIT_REPOSITORY https://github.com/bkaradzic/bgfx.cmake.git GIT_TAG ${ARMADA_BGFX_CMAKE_REV})
  FetchContent_MakeAvailable(bgfx_cmake)
  # Instance attributes cross to Direct3D as TEXCOORD<N> elements, and the renderer builds those
  # from BGFX_CONFIG_INSTANCE_DATA_FIRST_TEXCOORD. bgfx's default (31) is the DXIL layout: shaderc's
  # HLSL/SM5.0 emitter writes i_data0.. at TEXCOORD7 downwards (its remap table stops at
  # TexCoord15), so at the default the five instance vec4s name elements the shader never declares
  # and every hull draws with an unbound model matrix and tint - the whole world pass is garbage on
  # Windows while Metal is unaffected. Pin the backend to the semantics this build actually emits.
  target_compile_definitions(bgfx PRIVATE BGFX_CONFIG_INSTANCE_DATA_FIRST_TEXCOORD=7)
  # viewer.cpp directly consumes bx:: math; bgfx's private link does not export its headers.
  set(ARMADA_BGFX_TARGET bgfx bx)
  set(SHADERC_COMMAND $<TARGET_FILE:shaderc>)
  set(SHADERC_DEPENDENCY shaderc)
  # bgfx.cmake fetches bgfx itself, and the BGFX_DIR it sets lives in that subproject's directory
  # scope: here it is empty, so shaderc was invited to `-i /src` and no shader could open
  # bgfx_shader.sh ("error : Could not open include file 'bgfx_shader.sh'" on the Windows package
  # job, which is the only place this branch runs - local builds use the prebuilt shaderc). Derive
  # the directory from the fetched tree, search for it if the layout moves, and refuse to build
  # rather than pass an include path that cannot contain the header.
  set(ARMADA_BGFX_SHADER_INCLUDE "")
  foreach(candidate
      "${bgfx_cmake_SOURCE_DIR}/bgfx/src"
      "${CMAKE_BINARY_DIR}/_deps/bgfx_source-src/src"
      "${BGFX_DIR}/src")
    if(EXISTS "${candidate}/bgfx_shader.sh")
      set(ARMADA_BGFX_SHADER_INCLUDE "${candidate}")
      break()
    endif()
  endforeach()
  if(NOT ARMADA_BGFX_SHADER_INCLUDE)
    file(GLOB_RECURSE _bgfx_shader_headers "${CMAKE_BINARY_DIR}/_deps/*bgfx_shader.sh")
    list(FILTER _bgfx_shader_headers INCLUDE REGEX "/src/bgfx_shader\\.sh$")
    list(LENGTH _bgfx_shader_headers _bgfx_shader_count)
    if(_bgfx_shader_count GREATER 0)
      list(GET _bgfx_shader_headers 0 _bgfx_shader_header)
      get_filename_component(ARMADA_BGFX_SHADER_INCLUDE "${_bgfx_shader_header}" DIRECTORY)
    endif()
  endif()
  if(NOT ARMADA_BGFX_SHADER_INCLUDE)
    message(FATAL_ERROR "bgfx_shader.sh is not under ${CMAKE_BINARY_DIR}/_deps: shaderc needs its "
                        "directory on the include path, and guessing one produced unusable shaders")
  endif()
  message(STATUS "armada: bgfx shader include ${ARMADA_BGFX_SHADER_INCLUDE}")
endif()
set(JSON_BuildTests OFF CACHE BOOL "" FORCE)
FetchContent_Declare(json GIT_REPOSITORY https://github.com/nlohmann/json.git GIT_TAG 65ee68451d8eb2b5f3a30b410476ab83deb3289b)
FetchContent_MakeAvailable(json)
FetchContent_Declare(picosha2 GIT_REPOSITORY https://github.com/okdshin/PicoSHA2.git GIT_TAG 161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29)
FetchContent_GetProperties(picosha2)
if(NOT picosha2_POPULATED)
  FetchContent_Populate(picosha2)
endif()

if(APPLE)
  set(SHADER_PLATFORM osx)
  set(SHADER_PROFILE metal)
elseif(WIN32)
  set(SHADER_PLATFORM windows)
  set(SHADER_PROFILE s_5_0)
else()
  message(FATAL_ERROR "W01 native targets are macOS Metal and Windows Direct3D12")
endif()
set(SHADER_OUTPUTS)
foreach(NAME vs_fleet fs_fleet vs_shadow fs_shadow vs_ui fs_ui vs_top_hud fs_top_hud vs_planet fs_planet vs_mark fs_mark
        vs_fog fs_fog vs_shield fs_shield vs_star fs_star)
  if(NAME MATCHES "^vs_")
    set(TYPE vertex)
  else()
    set(TYPE fragment)
  endif()
  set(OUT "${CMAKE_CURRENT_BINARY_DIR}/shaders/${NAME}.bin")
  add_custom_command(OUTPUT "${OUT}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/shaders"
    COMMAND ${SHADERC_COMMAND} -f "${CMAKE_CURRENT_SOURCE_DIR}/shaders/${NAME}.sc" -o "${OUT}"
      --type ${TYPE} --platform ${SHADER_PLATFORM} --profile ${SHADER_PROFILE}
      -i "${ARMADA_BGFX_SHADER_INCLUDE}" --varyingdef "${CMAKE_CURRENT_SOURCE_DIR}/shaders/varying.def.sc"
    DEPENDS ${SHADERC_DEPENDENCY} "shaders/${NAME}.sc" "shaders/varying.def.sc" VERBATIM)
  list(APPEND SHADER_OUTPUTS "${OUT}")
endforeach()
add_custom_target(armada_shaders DEPENDS ${SHADER_OUTPUTS})
add_library(armada_scene INTERFACE)
target_include_directories(armada_scene INTERFACE include "${picosha2_SOURCE_DIR}")
target_link_libraries(armada_scene INTERFACE nlohmann_json::nlohmann_json)
add_library(armada_top_hud STATIC src/top_hud.cpp)
set_target_properties(armada_top_hud PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(armada_top_hud PUBLIC armada_scene)
add_library(armada_vector_hud STATIC src/vector_hud.cpp)
set_target_properties(armada_vector_hud PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(armada_vector_hud PUBLIC armada_top_hud)
add_executable(armada_viewer src/viewer.cpp)
target_link_libraries(armada_viewer PRIVATE armada_scene armada_vector_hud ${ARMADA_BGFX_TARGET} SDL3::SDL3)
target_compile_definitions(armada_viewer PRIVATE ARMADA_SHADER_DIR="${CMAKE_CURRENT_BINARY_DIR}/shaders")
add_dependencies(armada_viewer armada_shaders)
# The production game presents this windowless bgfx target in its original pygame window.
add_library(armada_embedded SHARED src/viewer.cpp)
target_link_libraries(armada_embedded PRIVATE armada_scene armada_vector_hud ${ARMADA_BGFX_TARGET} SDL3::SDL3)
target_compile_definitions(armada_embedded PRIVATE ARMADA_EMBEDDED_BUILD=1
  ARMADA_SHADER_DIR="${CMAKE_CURRENT_BINARY_DIR}/shaders")
add_dependencies(armada_embedded armada_shaders)

enable_testing()
add_executable(test_vector_hud tests/test_vector_hud.cpp)
target_link_libraries(test_vector_hud PRIVATE armada_vector_hud)
if(MSVC)
  target_compile_options(test_vector_hud PRIVATE /UNDEBUG)
else()
  target_compile_options(test_vector_hud PRIVATE -UNDEBUG)
endif()
target_compile_definitions(test_vector_hud PRIVATE ARMADA_ASSET_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/..")
add_test(NAME vector_hud COMMAND test_vector_hud)
add_executable(test_top_hud tests/test_top_hud.cpp)
target_link_libraries(test_top_hud PRIVATE armada_top_hud)
if(MSVC)
  target_compile_options(test_top_hud PRIVATE /UNDEBUG)
else()
  target_compile_options(test_top_hud PRIVATE -UNDEBUG)
endif()
target_compile_definitions(test_top_hud PRIVATE ARMADA_ASSET_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/..")
add_test(NAME top_hud COMMAND test_top_hud)
add_executable(test_scene tests/test_scene.cpp)
target_link_libraries(test_scene PRIVATE armada_scene)
add_test(NAME scene COMMAND test_scene)
add_executable(test_camera tests/test_camera.cpp)
target_include_directories(test_camera PRIVATE include)
add_test(NAME camera COMMAND test_camera)
add_executable(test_projectile tests/test_projectile.cpp)
target_include_directories(test_projectile PRIVATE include)
add_test(NAME projectiles COMMAND test_projectile)
# W02 consumer: decodes frames authored by the Python producer (tools/render/
# write_frame_fixtures.py). Header-only and GPU-free on purpose -- the risky half of the
# consumer is refusing malformed bytes, which needs no device.
# W03 consumer: decodes overlay payloads authored by tools/render/write_frame_fixtures.py.
add_executable(test_overlay tests/test_overlay.cpp)
target_link_libraries(test_overlay PRIVATE armada_scene)
target_compile_definitions(test_overlay PRIVATE
  ARMADA_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
add_test(NAME overlay COMMAND test_overlay)
# W04: the native input codec must produce the same bytes as the Python encoder
# (tools/render/write_input_fixtures.py writes the fixtures into tests/fixtures/input).
add_executable(test_input tests/test_input.cpp)
target_include_directories(test_input PRIVATE include)
add_test(NAME input COMMAND test_input)
set_tests_properties(input PROPERTIES ENVIRONMENT
  "ARMADA_INPUT_FIXTURE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/input")
add_executable(test_planets tests/test_planets.cpp)
target_include_directories(test_planets PRIVATE include)
target_compile_definitions(test_planets PRIVATE
  ARMADA_PLANET_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/planets")
add_executable(test_markers tests/test_markers.cpp)
target_include_directories(test_markers PRIVATE include)
add_test(NAME markers COMMAND test_markers)
set_tests_properties(markers PROPERTIES ENVIRONMENT
  "ARMADA_MARKER_FIXTURE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/markers")
add_executable(test_explosion tests/test_explosion.cpp)
target_include_directories(test_explosion PRIVATE include)
add_test(NAME explosions COMMAND test_explosion)
add_test(NAME planets COMMAND test_planets)
set_tests_properties(planets PROPERTIES ENVIRONMENT
  "ARMADA_PLANET_FIXTURE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/planets")
add_executable(test_shield tests/test_shield.cpp)
target_include_directories(test_shield PRIVATE include)
add_test(NAME shields COMMAND test_shield)

add_executable(test_hit tests/test_hit.cpp)
add_executable(dump_hit_geometry tools/dump_hit_geometry.cpp)
target_include_directories(dump_hit_geometry PRIVATE include)
target_include_directories(test_hit PRIVATE include)
add_test(NAME hits COMMAND test_hit)
add_executable(test_fogmap tests/test_fogmap.cpp)
target_include_directories(test_fogmap PRIVATE include)
target_compile_definitions(test_fogmap PRIVATE
  ARMADA_FOG_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/fog")
add_test(NAME fog COMMAND test_fogmap)
set_tests_properties(fog PROPERTIES ENVIRONMENT
  "ARMADA_FOG_FIXTURE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/fog")
add_executable(test_hardware tests/test_hardware.cpp)
target_include_directories(test_hardware PRIVATE include)
target_link_libraries(test_hardware PRIVATE armada_scene)
target_compile_definitions(test_hardware PRIVATE
  ARMADA_HARDWARE_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/hardware")
add_test(NAME hardware COMMAND test_hardware "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/hardware")
add_executable(test_frame_v2 tests/test_frame_v2.cpp)
target_link_libraries(test_frame_v2 PRIVATE armada_scene)
target_compile_definitions(test_frame_v2 PRIVATE
  ARMADA_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
add_test(NAME frame_v2 COMMAND test_frame_v2)
add_executable(test_starfield tests/test_starfield.cpp)
target_include_directories(test_starfield PRIVATE include)
add_test(NAME starfield COMMAND test_starfield)
