"""Cardboard Counter固有の「1カメラ2パレット」設定を一度だけ正規化する。"""

from __future__ import annotations

from typing import Any


PALLETS_PER_CAMERA = 2


def normalize_fixed_pallet_layout(value: Any) -> Any:
    """旧設定へカメラ内番号と不足枠を補う。既存枠は削除しない。"""
    if not isinstance(value, dict):
        return value
    cameras = value.get("cameras")
    pallets = value.get("pallets")
    if not isinstance(cameras, list) or not isinstance(pallets, list):
        return value
    camera_ids = [
        camera_data["camera_id"] for camera in cameras
        if (camera_data := mapping_copy(camera)) is not None
        and isinstance(camera_data.get("camera_id"), str)
    ]
    normalized = [mapping_copy(pallet) or pallet for pallet in pallets]
    used_ids = {
        pallet.get("pallet_id") for pallet in normalized
        if isinstance(pallet, dict) and isinstance(pallet.get("pallet_id"), int)
    }
    next_id = max(used_ids, default=0) + 1
    templates: dict[int, dict[str, Any]] = {}

    for camera_id in camera_ids:
        group = sorted(
            (
                pallet for pallet in normalized
                if isinstance(pallet, dict) and pallet.get("camera_id") == camera_id
            ),
            key=lambda pallet: int(pallet.get("pallet_id", 0)),
        )
        available = [1, 2]
        for index, pallet in enumerate(group):
            number = pallet.get("pallet_number")
            if not isinstance(number, int) or number not in available:
                number = available[0] if available else index + 1
                pallet["pallet_number"] = number
            if number in available:
                available.remove(number)
            if number in (1, 2):
                templates.setdefault(number, pallet)

        for number in available:
            template = templates.get(number)
            new_pallet = dict(template) if template is not None else default_pallet_payload(number)
            new_pallet.update({
                "pallet_id": next_id,
                "pallet_number": number,
                "camera_id": camera_id,
                "display_name": f"パレット {number}",
                "enabled": False,
            })
            next_id += 1
            normalized.append(new_pallet)
            templates.setdefault(number, new_pallet)

    result = dict(value)
    result["pallets"] = normalized
    return result


def mapping_copy(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="python")
        return dict(dumped) if isinstance(dumped, dict) else None
    return None


def default_pallet_payload(number: int) -> dict[str, Any]:
    if number == 1:
        plane_roi = [0.05, 0.15, 0.48, 0.95]
    else:
        plane_roi = [0.52, 0.15, 0.95, 0.95]
    return {
        "pallet_number": number,
        "display_name": f"パレット {number}",
        "enabled": False,
        "low_stock_threshold_liters": 5.0,
        "email_rearm_margin_liters": 154.0,
        "plane_roi": plane_roi,
        "single_box_labels": ["cardboard_box"],
        "mixed_box_groups": [],
        "reference_box_label": "cardboard_box",
    }
