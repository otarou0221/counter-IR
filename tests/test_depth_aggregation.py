import numpy as np

from cardboard_counter_v2.common.depth_aggregation import temporal_median_depth


def test_single_depth_frame_uses_direct_float32_result() -> None:
    frame = np.array([[0, 1000], [1200, 1300]], dtype=np.uint16)
    result = temporal_median_depth(frame[None, ...])

    assert result.dtype == np.float32
    np.testing.assert_array_equal(result, frame)


def test_multiple_depth_frames_still_ignore_zero_for_median() -> None:
    frames = np.array([[[0, 100]], [[200, 300]], [[400, 500]]], dtype=np.uint16)
    result = temporal_median_depth(frames)

    np.testing.assert_array_equal(result, np.array([[300, 300]], dtype=np.float32))
