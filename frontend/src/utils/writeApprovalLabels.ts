export function writeApprovalPrimaryLabel(fileCount?: number): string {
  if (fileCount && fileCount > 1) {
    return `Save all ${fileCount} files & continue`;
  }
  return "Save all files & continue";
}
