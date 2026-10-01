from cardboard_counter_v2.common.rgbd import (
    RgbdIntrinsics,
    StreamIntrinsics,
    intrinsics_compatible,
)


def camera(*, fx: float = 749.825684, width: int = 1280) -> RgbdIntrinsics:
    return RgbdIntrinsics(
        color=StreamIntrinsics(
            width=width,
            height=720,
            fx=fx,
            fy=749.919678,
            cx=646.577026,
            cy=337.566528,
        ),
        depth=None,
        align_depth_to_color=True,
        point_cloud_sensor="color",
    )


def test_xyz_recovered_intrinsics_accept_sub_millipixel_rounding() -> None:
    recovered = camera(fx=749.8256837913239)
    sdk = camera(fx=749.825684)
    assert intrinsics_compatible(recovered, sdk)


def test_material_intrinsics_change_is_rejected() -> None:
    assert not intrinsics_compatible(camera(), camera(fx=750.0))
    assert not intrinsics_compatible(camera(), camera(width=640))
