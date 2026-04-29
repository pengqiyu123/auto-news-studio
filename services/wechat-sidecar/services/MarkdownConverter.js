class MarkdownConverter {
  static convertToWeChatHTML(markdownContent) {
    if (!markdownContent || typeof markdownContent !== "string") {
      return "";
    }

    let html = markdownContent;
    html = html.replace(/```([\s\S]*?)```/g, (_match, code) => {
      return `<pre style="background:#f6f8fa;padding:16px;border-radius:8px;overflow:auto;"><code>${this.escapeHtml(code.trim())}</code></pre>`;
    });
    html = html.replace(/^# (.+)$/gm, "<h1 style=\"font-size:28px;line-height:1.35;margin:24px 0 16px;\">$1</h1>");
    html = html.replace(/^## (.+)$/gm, "<h2 style=\"font-size:22px;line-height:1.4;margin:18px 0 12px;\">$1</h2>");
    html = html.replace(/^### (.+)$/gm, "<h3 style=\"font-size:18px;line-height:1.4;margin:16px 0 10px;\">$1</h3>");
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*?<\/li>)/gs, "<ul style=\"padding-left:1.5rem;line-height:1.8;\">$1</ul>");
    html = html
      .split(/\n\s*\n/)
      .map((part) => {
        if (part.startsWith("<h") || part.startsWith("<ul") || part.startsWith("<pre")) {
          return part;
        }
        return `<p style="margin:0 0 1em 0;line-height:1.8;color:#222;">${part.replace(/\n/g, "<br/>")}</p>`;
      })
      .join("");
    return `<section style="font-size:15px;color:#222;">${html}</section>`;
  }

  static escapeHtml(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
}

export default MarkdownConverter;
