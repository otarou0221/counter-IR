"""設定から測定対象を選ぶ副作用のない共通関数。"""

from cardboard_counter_v2.common.schemas import PalletSettings, SystemSettings


def active_camera_ids(settings: SystemSettings) -> list[str]:
    enabled = {pallet.camera_id for pallet in settings.pallets if pallet.enabled}
    return [
        camera.camera_id
        for camera in settings.cameras
        if camera.camera_id in enabled
    ]


def pallets_for_camera(
    settings: SystemSettings,
    camera_id: str,
) -> list[PalletSettings]:
    return [
        pallet
        for pallet in settings.pallets
        if pallet.enabled and pallet.camera_id == camera_id
    ]
