export function fieldChanged<ObjectType extends object, Key extends keyof ObjectType>(
  current: ObjectType,
  saved: ObjectType | null | undefined,
  key: Key,
): boolean {
  return saved === null || saved === undefined || !Object.is(current[key], saved[key]);
}

export function valuesEqual(current: unknown, saved: unknown): boolean {
  if (Object.is(current, saved)) return true;
  if (current === null || saved === null) return false;
  if (typeof current !== "object" || typeof saved !== "object") return false;

  const currentIsArray = Array.isArray(current);
  if (currentIsArray !== Array.isArray(saved)) return false;
  if (currentIsArray) {
    const currentItems = current as unknown[];
    const savedItems = saved as unknown[];
    return currentItems.length === savedItems.length
      && currentItems.every((item, index) => valuesEqual(item, savedItems[index]));
  }

  const currentRecord = current as Record<string, unknown>;
  const savedRecord = saved as Record<string, unknown>;
  const currentKeys = Object.keys(currentRecord);
  const savedKeys = Object.keys(savedRecord);
  return currentKeys.length === savedKeys.length
    && currentKeys.every((key) => Object.prototype.hasOwnProperty.call(savedRecord, key)
      && valuesEqual(currentRecord[key], savedRecord[key]));
}

export function hasUnsavedChanges(current: unknown | null, saved: unknown | null): boolean {
  if (current === null) return false;
  return saved === null || !valuesEqual(current, saved);
}

export function structuredValueChanged(current: unknown, saved: unknown): boolean {
  return !valuesEqual(current, saved);
}
