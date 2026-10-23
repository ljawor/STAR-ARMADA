"""CPU-only regression for the GPU probe's text-AA acceptance criterion."""
import numpy as np
import pytest

from tools.render.probe_native_vector_hud import text_aa_ramp_pixels


def test_eight_opaque_foreground_pixels_are_not_antialiasing():
    background = np.full((2, 4, 3), (20, 40, 60), dtype=np.uint8)
    foreground = np.full_like(background, (220, 160, 100))
    count = text_aa_ramp_pixels(foreground, background, (220, 160, 100))
    assert count < 8, 'eight solid pixels must not satisfy the AA acceptance gate'
    assert count == 0


@pytest.mark.parametrize('coverage', [0, .01, .05, .95, .99, 1])
def test_background_and_near_endpoint_pixels_do_not_count(coverage):
    background = np.zeros((2, 4, 3), dtype=np.uint8)
    foreground = np.full_like(background, round(200 * coverage))
    assert text_aa_ramp_pixels(foreground, background, (200, 200, 200)) == 0


@pytest.mark.parametrize('coverage', [.1, .25, .5, .75, .9])
def test_eight_intermediate_color_consistent_pixels_pass(coverage):
    # Different local backgrounds, including channels darker than the background,
    # catch accidental uint8 subtraction/wraparound and global-background oracles.
    background = np.array([[[20, 40, 180], [40, 60, 200],
                            [60, 80, 220], [80, 100, 240]]] * 2, dtype=np.uint8)
    color = (220, 160, 100)
    foreground = np.rint(background.astype(float) * (1 - coverage)
                         + np.array(color) * coverage).astype(np.uint8)
    assert text_aa_ramp_pixels(foreground, background, color) == 8


def test_opaque_pixels_cannot_top_up_seven_real_ramp_pixels():
    background = np.zeros((2, 4, 3), dtype=np.uint8)
    foreground = np.full_like(background, 100)
    foreground[0, 0] = 200
    assert text_aa_ramp_pixels(foreground, background, (200, 200, 200)) == 7


def test_intermediate_but_wrong_color_is_not_a_text_ramp():
    background = np.zeros((2, 4, 3), dtype=np.uint8)
    # Projects to .5 coverage, but differs by 20 from the expected grey ramp.
    foreground = np.full_like(background, (120, 80, 100))
    assert text_aa_ramp_pixels(foreground, background, (200, 200, 200)) == 0


def test_insufficient_foreground_background_contrast_does_not_count():
    background = np.full((2, 4, 3), 100, dtype=np.uint8)
    foreground = np.full_like(background, 102)
    assert text_aa_ramp_pixels(foreground, background, (104, 104, 104)) == 0
