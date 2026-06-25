export function writeApprovalPrimaryLabel(fileCount?: number): string {
  if (fileCount && fileCount > 1) {
    return `Save all ${fileCount} files & continue`;
  }
  return "Save all files & continue";
}

/** Footer / header label while a background save is already running. */
export function writeApprovalSaveInProgressLabel(fileCount?: number): string {
  if (fileCount && fileCount > 1) {
    return `Saving ${fileCount} files to disk — please wait…`;
  }
  return "Saving to disk — please wait…";
}
