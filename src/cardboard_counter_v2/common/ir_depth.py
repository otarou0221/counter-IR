"""Active IR と未整列Depthが同じ画素格子を使うことを検証する。"""

from __future__ import annotations

from cardboard_counter_v2.common.rgbd import RgbdIntrinsics


def validate_ir_depth_geometry(
    intrinsics: RgbdIntrinsics,
    ir_shape: tuple[int, int],
    depth_shape: tuple[int, int],
) -> None:
    """ROI画像とXYZの画素が1対1で対応する場合だけ通す。"""
    if intrinsics.align_depth_to_color or intrinsics.point_cloud_sensor != "depth":
        raise ValueError("Active IR版には未整列のDepth座標が必要です")
    if ir_shape != depth_shape:
        raise ValueError(f"IRとDepthの画素数が違います: {ir_shape} != {depth_shape}")
    for name, profile in (("IR", intrinsics.ir), ("Depth", intrinsics.depth)):
        if profile is None or (profile.height, profile.width) != depth_shape:
            raise ValueError(f"{name}内部パラメータが画像解像度と一致しません")
    ir = intrinsics.ir
    depth = intrinsics.depth
    assert ir is not None and depth is not None
    # Femto MegaのActive IR/Depthは同じToF画素を使う。SDKから返る
    # 投影値がずれた場合、見かけ上同サイズでもROIの対応を保証できない。
    if any(abs(getattr(ir, key) - getattr(depth, key)) > 1.0 for key in ("fx", "fy", "cx", "cy")):
        raise ValueError("IRとDepthの内部パラメータが一致しません")
    if (ir.distortion is None) != (depth.distortion is None):
        raise ValueError("IRとDepthの歪み係数が一致しません")
    if ir.distortion is not None and depth.distortion is not None:
        if any(
            abs(getattr(ir.distortion, key) - getattr(depth.distortion, key)) > 1e-4
            for key in vars(ir.distortion)
        ):
            raise ValueError("IRとDepthの歪み係数が一致しません")
