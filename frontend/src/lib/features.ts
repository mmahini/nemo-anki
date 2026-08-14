import { useAuth } from "../auth/AuthContext";
import type { AuthUser } from "../auth/api";

/** Feature flags — must mirror backend apps/accounts/feature_flags.py. */
export const FLAGS = {
  /** Staff-only tooling: book upload and the My Books area. */
  STAFF: "staff",
} as const;

export type FeatureFlag = (typeof FLAGS)[keyof typeof FLAGS];

export function hasFlag(user: AuthUser | null, flag: FeatureFlag): boolean {
  return !!user?.feature_flags?.includes(flag);
}

/** Hook: is the given feature flag enabled for the signed-in user? */
export function useFlag(flag: FeatureFlag): boolean {
  const { user } = useAuth();
  return hasFlag(user, flag);
}

/** Build-time switch for automatic image lookup ("Find image" / 🖼️ buttons).
 *
 * Unlike FLAGS above this is not per-user — it is baked into the bundle. Off by
 * default: the pictures it finds are usually a poor match for the word. Manual
 * photo upload is unaffected. Must match the backend's
 * CARD_IMAGE_SEARCH_ENABLED — set both to turn the feature back on. */
export const CARD_IMAGE_SEARCH_ENABLED = import.meta.env.VITE_CARD_IMAGE_SEARCH === "1";
