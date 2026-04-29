import express from "express";

import MarkdownConverter from "./services/MarkdownConverter.js";
import WeChatAPI from "./services/WeChatAPI.js";

const app = express();
app.use(express.json({ limit: "2mb" }));

app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "wechat-sidecar" });
});

app.post("/convert", (req, res) => {
  const markdown = req.body?.markdown ?? "";
  res.json({
    status: "ok",
    html: MarkdownConverter.convertToWeChatHTML(markdown),
  });
});

app.post("/draft", async (req, res) => {
  const { appId, appSecret, title, content, author = "", thumbMediaId = null } = req.body ?? {};
  const api = new WeChatAPI(appId, appSecret);
  try {
    const result = await api.createDraft({ title, content, author, thumbMediaId });
    res.json({ status: "ok", ...result });
  } catch (error) {
    res.status(500).json({ status: "error", message: error.message });
  }
});

app.post("/publish", async (req, res) => {
  const { appId, appSecret, mediaId } = req.body ?? {};
  const api = new WeChatAPI(appId, appSecret);
  try {
    const result = await api.publishDraft({ mediaId });
    res.json({ status: "ok", ...result });
  } catch (error) {
    res.status(500).json({ status: "error", message: error.message });
  }
});

app.get("/status/:publishId", async (req, res) => {
  const { appId, appSecret } = req.query;
  const api = new WeChatAPI(appId, appSecret);
  try {
    const result = await api.getPublishStatus(req.params.publishId);
    res.json({ status: "ok", ...result });
  } catch (error) {
    res.status(500).json({ status: "error", message: error.message });
  }
});

const port = Number(process.env.PORT || 8091);
app.listen(port, "127.0.0.1", () => {
  console.log(`wechat-sidecar listening on http://127.0.0.1:${port}`);
});
