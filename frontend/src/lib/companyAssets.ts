/** Codes are stable API identifiers; labels and roles come from the server catalog. */
export type AssetCategory =
  | "business_registration"
  | "corporate_register"
  | "credit_rating"
  | "sme_certificate"
  | "insurance_payment"
  | "seal_certificate"
  | "other_evidence"
  | "previous_proposal"
  | "product_catalogue";

export interface AssetCategoryRecord {
  code: AssetCategory;
  label: string;
  role: "company_evidence" | "company_reference" | "product_evidence";
}

export interface AssetCategoryCatalog {
  version: string;
  sha256: string;
  items: AssetCategoryRecord[];
}

/** Older or malformed catalog responses keep file access, but cannot classify new files. */
export function categoryOptions(catalog?: AssetCategoryCatalog): AssetCategoryRecord[] {
  if (!catalog || !catalog.version || !catalog.sha256 || !Array.isArray(catalog.items)) return [];
  const items = catalog.items;
  if (!items.length || items.some(item => !item || typeof item.code !== "string" || !item.code
    || typeof item.label !== "string" || !item.label.trim()
    || !["company_evidence", "company_reference", "product_evidence"].includes(item.role))
    || new Set(items.map(item => item.code)).size !== items.length) return [];
  return items;
}
