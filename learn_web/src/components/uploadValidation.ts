export function validateUpload(files: readonly File[]): string | undefined {
  if (files.length > 10) return "每批最多上传 10 份资料，请减少选择。";
  if (files.reduce((sum, file) => sum + file.size, 0) > 100 * 1024 * 1024)
    return "每批文件总量最多 100 MB，请分批上传。";
  const invalid = files.find(
    (file) => !file.size || file.size > 50 * 1024 * 1024,
  );
  if (invalid) return `「${invalid.name}」：请选择非空且不超过 50 MB 的文件。`;
  const unsupported = files.find(
    (file) => !/\.(txt|md|pdf|docx)$/i.test(file.name),
  );
  if (unsupported)
    return `「${unsupported.name}」：仅支持 TXT、Markdown、PDF 和 DOCX。`;
}
