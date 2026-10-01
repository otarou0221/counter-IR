from __future__ import annotations

import numpy as np
import pytest

from cardboard_counter_v2.camera.ir_preview import ir_preview


def test_gamma_brightens_display_midtones_without_changing_raw_ir() -> None:
    raw = np.array([[0, 100, 200, 300, 400, 500]], dtype=np.uint16)
    original = raw.copy()
    linear = ir_preview(raw, gamma=1.0)
    brighter = ir_preview(raw, gamma=0.55)

    assert brighter.dtype == np.uint8
    assert brighter[0, 0] == 0
    assert brighter[0, 2] > linear[0, 2]
    assert brighter[0, -1] == 255
    np.testing.assert_array_equal(raw, original)


def test_empty_ir_stays_black_and_invalid_gamma_is_rejected() -> None:
    black = np.zeros((4, 4), dtype=np.uint16)
    np.testing.assert_array_equal(ir_preview(black), np.zeros_like(black, dtype=np.uint8))
    with pytest.raises(ValueError, match="IR_PREVIEW_GAMMA"):
        ir_preview(np.ones((4, 4), dtype=np.uint16), gamma=0.0)
