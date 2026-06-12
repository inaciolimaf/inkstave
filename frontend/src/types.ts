/** TypeScript mirrors of the backend Pydantic shapes (specs 06-08). */

export interface UserPublic {
  id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  email_confirmed: boolean;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

/** Field-scoped validation errors keyed by field name (from a 422 envelope). */
export type FieldErrors = Record<string, string>;
