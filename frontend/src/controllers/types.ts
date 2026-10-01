export type RunOperation = (action: () => Promise<void>) => Promise<void>;
