"""Orbbec設定をベンダー非依存のフレームソース登録へ接続する。"""

from cardboard_counter_v2.camera.orbbec_source import (
    OrbbecFrameSource,
    OrbbecSourceConfig,
)
from cardboard_counter_v2.camera.source import FrameSourceRegistry, IrDepthFrameSource
from cardboard_counter_v2.common.camera_contracts import CameraDeviceSettings


def create_orbbec_source(camera: CameraDeviceSettings) -> IrDepthFrameSource:
    return OrbbecFrameSource(
        OrbbecSourceConfig(
            ip=camera.ip,
            port=camera.port,
            width=camera.width,
            height=camera.height,
            depth_width=camera.depth_width,
            depth_height=camera.depth_height,
            fps=camera.fps,
            max_frames=0,
            auto_build=False,
        )
    )


def default_source_registry() -> FrameSourceRegistry:
    registry = FrameSourceRegistry()
    registry.register("orbbec_network", create_orbbec_source)
    return registry
