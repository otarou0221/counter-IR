import type { CameraSettings, PalletSettings } from "./types";

export const PALLETS_PER_CAMERA = 2;

export function createPalletPair(cameraId: string, pallets: PalletSettings[]): PalletSettings[] {
  const templateCameraId = pallets[0]?.camera_id;
  const templates = pallets
    .filter((pallet) => pallet.camera_id === templateCameraId)
    .sort((left, right) => left.pallet_number - right.pallet_number);
  let nextId = Math.max(0, ...pallets.map((pallet) => pallet.pallet_id)) + 1;
  return [1, 2].map((palletNumber) => {
    const template = templates.find((pallet) => pallet.pallet_number === palletNumber);
    if (!template) throw new Error(`パレット${palletNumber}の複製元がありません`);
    const palletId = nextId++;
    return {
      ...template,
      pallet_id: palletId,
      pallet_number: palletNumber,
      camera_id: cameraId,
      display_name: `パレット ${palletNumber}`,
      enabled: false,
    };
  });
}

export function validFixedPalletLayout(
  cameras: CameraSettings[], pallets: PalletSettings[],
): boolean {
  const ids = new Set<number>();
  for (const pallet of pallets) {
    if (ids.has(pallet.pallet_id)) return false;
    ids.add(pallet.pallet_id);
  }
  return cameras.every((camera) => {
    const numbers = pallets
      .filter((pallet) => pallet.camera_id === camera.camera_id)
      .map((pallet) => pallet.pallet_number)
      .sort();
    return numbers.length === PALLETS_PER_CAMERA && numbers[0] === 1 && numbers[1] === 2;
  }) && pallets.every((pallet) => cameras.some((camera) => camera.camera_id === pallet.camera_id));
}
