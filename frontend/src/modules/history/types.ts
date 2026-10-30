/** History domain types mirroring the spec-37 API. */

export interface Author {
  id: string;
  name: string;
  email: string;
}

export interface LabelBrief {
  id: string;
  name: string;
}

export interface Version {
  version: number;
  timestamp: string;
  author: Author | null;
  opCount: number;
  size: number;
  labels: LabelBrief[];
}

export interface VersionsPage {
  docId: string;
  currentVersion: number;
  versions: Version[];
  hasMore: boolean;
  nextBefore: number | null;
}

export type SegmentType = "context" | "added" | "removed";

export interface DiffSegment {
  type: SegmentType;
  value: string;
}

export interface DiffHunk {
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  segments: DiffSegment[];
}

export interface DiffResult {
  from: number;
  to: number | "current";
  binary: boolean;
  tooLarge: boolean;
  hunks: DiffHunk[];
}

export interface HistoryLabel {
  id: string;
  name: string;
  version: number;
  docId: string | null;
  createdBy: string | null;
  createdAt: string;
}

export interface RestoreResult {
  docId: string;
  restoredFromVersion: number;
  newVersion: number;
  label: HistoryLabel | null;
}
