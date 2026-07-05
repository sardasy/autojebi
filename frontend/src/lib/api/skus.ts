import { postJson } from "./client";

export interface IngestRequest {
  source?: string;
  skus?: unknown[];
}

export interface IngestResult {
  ingested: number;
  collection: string;
}

export async function ingestSkus(payload: IngestRequest = {}): Promise<IngestResult> {
  return postJson<IngestResult>("/skus/ingest", payload);
}
