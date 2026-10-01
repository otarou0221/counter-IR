"""共通箱カタログと旧パレット別寸法の一回性移行。"""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, Field, model_validator


class BoxClassSpec(BaseModel):
    box_type_id: int | None = Field(default=None, ge=1)
    label: str = Field(min_length=1, max_length=100)
    width_mm: float = Field(gt=0)
    depth_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)

    @model_validator(mode="after")
    def normalize_label(self) -> "BoxClassSpec":
        label = self.label.strip()
        if not label:
            raise ValueError("箱クラス名は空欄にできません")
        self.label = label
        return self

    @property
    def volume_mm3(self) -> float:
        return self.width_mm * self.depth_mm * self.height_mm


def default_box_catalog() -> list[BoxClassSpec]:
    return [
        BoxClassSpec(
            label="cardboard_box",
            width_mm=570.0,
            depth_mm=410.0,
            height_mm=335.0,
        )
    ]


def migrate_legacy_box_settings(value: Any) -> Any:
    """旧パレット内の箱寸法を共通カタログとラベル選択へ変換する。"""
    if not isinstance(value, dict):
        return value
    payload = dict(value)
    pallets = [dict(item) for item in payload.get("pallets", []) if isinstance(item, dict)]
    catalog = _validated_specs(payload.get("box_catalog", []))
    by_label = {item.label.casefold(): item for item in catalog}

    for pallet in pallets:
        legacy_specs = _pallet_legacy_specs(pallet)
        if legacy_specs:
            selected: list[str] = []
            for spec in legacy_specs:
                selected.append(
                    _merge_spec(
                        catalog,
                        by_label,
                        spec,
                        pallet_id=pallet.get("pallet_id", 1),
                    )
                )
            pallet.setdefault("single_box_labels", selected)
            pallet.setdefault("reference_box_label", selected[0])
        pallet.pop("box_classes", None)
        pallet.pop("box_width_mm", None)
        pallet.pop("box_depth_mm", None)
        pallet.pop("box_height_mm", None)

    if not catalog:
        catalog = default_box_catalog()
    payload["box_catalog"] = [item.model_dump() for item in catalog]
    if pallets:
        payload["pallets"] = pallets
    return payload


def catalog_by_label(catalog: Iterable[BoxClassSpec]) -> dict[str, BoxClassSpec]:
    return {item.label.casefold(): item for item in catalog}


def validate_box_selections(
    catalog: list[BoxClassSpec],
    selections: Iterable[tuple[int, list[str], list[list[str]], str]],
) -> None:
    indexed = catalog_by_label(catalog)
    if len(indexed) != len(catalog):
        raise ValueError("共通箱カタログのクラス名が重複しています")
    for pallet_id, single_labels, mixed_groups, reference_label in selections:
        labels = single_labels + [label for group in mixed_groups for label in group]
        unknown = [label for label in labels if label.casefold() not in indexed]
        if unknown:
            raise ValueError(
                f"パレット{pallet_id}の箱クラスがカタログにありません: {', '.join(unknown)}"
            )
        if reference_label.casefold() not in {label.casefold() for label in labels}:
            raise ValueError(f"パレット{pallet_id}の基準箱が対象クラスにありません")


def _validated_specs(raw_specs: object) -> list[BoxClassSpec]:
    if not isinstance(raw_specs, list):
        return []
    return [BoxClassSpec.model_validate(item) for item in raw_specs]


def _pallet_legacy_specs(pallet: dict[str, Any]) -> list[BoxClassSpec]:
    raw_classes = pallet.get("box_classes")
    if isinstance(raw_classes, list) and raw_classes:
        return [BoxClassSpec.model_validate(item) for item in raw_classes]
    legacy_keys = ("box_width_mm", "box_depth_mm", "box_height_mm")
    if not any(key in pallet for key in legacy_keys):
        return []
    return [
        BoxClassSpec(
            label="cardboard_box",
            width_mm=pallet.get("box_width_mm", 570.0),
            depth_mm=pallet.get("box_depth_mm", 410.0),
            height_mm=pallet.get("box_height_mm", 335.0),
        )
    ]


def _merge_spec(
    catalog: list[BoxClassSpec],
    by_label: dict[str, BoxClassSpec],
    spec: BoxClassSpec,
    *,
    pallet_id: object,
) -> str:
    key = spec.label.casefold()
    existing = by_label.get(key)
    if existing is None:
        catalog.append(spec)
        by_label[key] = spec
        return spec.label
    if _same_dimensions(existing, spec):
        return existing.label

    base = f"{spec.label}_p{pallet_id}"
    label = base
    suffix = 2
    while label.casefold() in by_label:
        label = f"{base}_{suffix}"
        suffix += 1
    renamed = spec.model_copy(update={"label": label})
    catalog.append(renamed)
    by_label[label.casefold()] = renamed
    return label


def _same_dimensions(left: BoxClassSpec, right: BoxClassSpec) -> bool:
    return (
        left.width_mm == right.width_mm
        and left.depth_mm == right.depth_mm
        and left.height_mm == right.height_mm
    )
