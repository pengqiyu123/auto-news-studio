export function formatRuntimeIssueLabel(sourceName: string | null | undefined, message: string) {
  return `${sourceName?.trim() ? `${sourceName}: ` : "系统异常："}${message}`;
}
