export type UploadFile = { file: File; path: string };
export type SelectedUpload = UploadFile & { id: number };
export const candidates = (files: File[]): UploadFile[] =>
  files.map((file) => ({ file, path: file.webkitRelativePath || file.name }));

export function uploadIssue(value: UploadFile): string | null {
  const path = value.path.toLowerCase();
  const name = path.split("/").pop() ?? path;
  const stem = name.replace(/\.[^.]+$/, "");
  if (
    path
      .split("/")
      .some((part) =>
        ["keys", "answer_keys", "answer-keys", "holdout"].includes(part),
      ) ||
    stem.endsWith("_key") ||
    stem.includes("answer_key") ||
    stem.includes("expected_result") ||
    name === "index.csv"
  )
    return "Answer keys and evaluation metadata cannot be scanned.";
  if (!/\.(pdf|docx)$/i.test(name))
    return "Unsupported format. Remove this file to continue.";
  if (value.file.size > 25 * 1024 ** 2)
    return "Exceeds 25 MiB. Remove this file to continue.";
  return null;
}

export async function droppedFiles(
  items: DataTransferItemList,
  fallback: FileList,
): Promise<UploadFile[]> {
  const files: UploadFile[] = [];
  async function walk(entry: FileSystemEntry): Promise<void> {
    if (entry.isFile) {
      if (files.length >= 100)
        throw new Error("Choose at most 100 files per batch.");
      const file = await new Promise<File>((resolve, reject) =>
        (entry as FileSystemFileEntry).file(resolve, reject),
      );
      files.push({ file, path: entry.fullPath.replace(/^\//, "") });
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      while (true) {
        const children = await new Promise<FileSystemEntry[]>(
          (resolve, reject) => reader.readEntries(resolve, reject),
        );
        if (!children.length) break;
        for (const child of children) await walk(child);
      }
    }
  }
  const entries = Array.from(items)
    .map((item) => item.webkitGetAsEntry?.())
    .filter((entry): entry is FileSystemEntry => !!entry);
  if (!entries.length) return candidates(Array.from(fallback));
  for (const entry of entries) await walk(entry);
  return files;
}
