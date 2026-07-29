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
