"""Real compatibility-context ownership probe; never use SDL's dummy driver.

Run: PYTHONPATH=. .venv/bin/python tools/diag_gl_lifecycle.py
"""
import pygame
from OpenGL import GL
from unittest.mock import patch

from game.data.store import DataStore
from game.core.manager import GameManager
from render.camera import Camera
from render.renderer import Renderer
from render.hud import HUD
from render import textures
from render.fleet_materials import FleetMaterials


def no_errors(label):
    error = GL.glGetError()
    assert error == GL.GL_NO_ERROR, (label, error)


def main():
    pygame.init()
    pygame.display.set_mode((640, 480), pygame.OPENGL | pygame.DOUBLEBUF)
    pygame.event.pump()
    print('GL', GL.glGetString(GL.GL_VERSION).decode())
    ds = DataStore.get()
    state = GameManager.start_skirmish(ds.maps['skirmish01']).state
    camera = Camera(640, 480)
    sentinel = textures.surface_to_texture(pygame.Surface((2, 2)))
    try:
        for cycle in range(3):
            renderer = Renderer(state, camera)
            hud = HUD(640, 480, state)
            assert renderer.materials.available, renderer.materials.error
            camera.apply()
            GL.glBindTexture(GL.GL_TEXTURE_2D, sentinel)
            renderer._draw_starfield()
            assert int(GL.glGetIntegerv(GL.GL_TEXTURE_BINDING_2D)) == sentinel
            renderer.draw(0.0, set())
            # Touch each lazy ownership slot even if its object is off-screen.
            for attr in ('_hull_tex', '_space_tex', '_star_tex', '_nebula_tex'):
                if getattr(renderer, attr) is None:
                    setattr(renderer, attr, textures.surface_to_texture(pygame.Surface((2, 2))))
            for entity in state.entities.values():
                if entity.is_planet:
                    renderer._planet_texture_for(entity)
            renderer._ship_display_list('wedge')
            hud.render(set(), None, 0, False)
            hud.draw_gl()
            programs = set(renderer.materials.programs.values())
            lists = set(renderer.ship_lists.values()) | {renderer._star_list, renderer._unit_sphere_tex}
            tex_ids = set(renderer._planet_tex_cache.values()) | {
                renderer._hull_tex, renderer._space_tex, renderer._star_tex,
                renderer._nebula_tex, hud.tex}
            assert all(GL.glIsProgram(p) for p in programs)
            assert all(GL.glIsList(p) for p in lists)
            assert all(GL.glIsTexture(p) for p in tex_ids)
            no_errors('created/drawn')
            renderer.close()
            hud.close()
            assert not any(GL.glIsProgram(p) for p in programs)
            assert not any(GL.glIsList(p) for p in lists)
            assert not any(GL.glIsTexture(p) for p in tex_ids)
            assert GL.glIsTexture(sentinel), 'deleted an unowned texture'
            renderer.close()
            hud.close()
            no_errors('closed twice')
            print(f'CYCLE {cycle + 1}: deleted programs={len(programs)} textures={len(tex_ids)} lists={len(lists)}; GL_NO_ERROR')

        # Real compiler failure: capture allocations and prove failed shader gone.
        allocated = []
        create = GL.glCreateShader
        def capture(kind):
            shader = create(kind)
            allocated.append(shader)
            return shader
        with patch('render.fleet_materials.VERTEX', '#version 120\ninvalid shader'), \
             patch.object(GL, 'glCreateShader', side_effect=capture):
            material = FleetMaterials()
        assert material.error and not material.available
        assert allocated and not any(GL.glIsShader(s) for s in allocated)
        material.close()
        no_errors('compile fallback')
        print('COMPILE_FAILURE: owned shader deleted; GL_NO_ERROR')
        print('GL_LIFECYCLE_OK')
    finally:
        GL.glDeleteTextures([sentinel])
        pygame.quit()


if __name__ == '__main__':
    main()
