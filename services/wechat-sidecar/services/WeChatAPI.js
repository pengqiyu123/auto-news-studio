import axios from "axios";

class WeChatAPI {
  constructor(appId, appSecret) {
    this.appId = appId;
    this.appSecret = appSecret;
    this.accessToken = null;
    this.expireAt = 0;
  }

  async getAccessToken() {
    const now = Date.now();
    if (this.accessToken && now < this.expireAt) {
      return this.accessToken;
    }
    if (!this.appId || !this.appSecret) {
      throw new Error("缺少 AppID 或 AppSecret");
    }
    const response = await axios.get("https://api.weixin.qq.com/cgi-bin/token", {
      params: {
        grant_type: "client_credential",
        appid: this.appId,
        secret: this.appSecret,
      },
      timeout: 10000,
    });
    if (!response.data?.access_token) {
      throw new Error(response.data?.errmsg || "获取 access_token 失败");
    }
    this.accessToken = response.data.access_token;
    this.expireAt = now + (response.data.expires_in - 60) * 1000;
    return this.accessToken;
  }

  async createDraft({ title, content, author, thumbMediaId }) {
    const token = await this.getAccessToken();
    const article = {
      title,
      author: author || "",
      digest: content.replace(/<[^>]+>/g, "").slice(0, 110),
      content,
      content_source_url: "",
      need_open_comment: 0,
      only_fans_can_comment: 0,
    };
    if (thumbMediaId) {
      article.thumb_media_id = thumbMediaId;
    }
    const response = await axios.post(
      `https://api.weixin.qq.com/cgi-bin/draft/add?access_token=${token}`,
      { articles: [article] },
      { timeout: 30000 }
    );
    if (response.data?.errcode && response.data.errcode !== 0) {
      throw new Error(response.data.errmsg || "创建微信草稿失败");
    }
    return { mediaId: response.data.media_id };
  }

  async publishDraft({ mediaId }) {
    const token = await this.getAccessToken();
    const response = await axios.post(
      `https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token=${token}`,
      { media_id: mediaId },
      { timeout: 30000 }
    );
    if (response.data?.errcode && response.data.errcode !== 0) {
      throw new Error(response.data.errmsg || "提交发布失败");
    }
    return {
      publishId: response.data.publish_id,
      msgId: response.data.msg_id,
    };
  }

  async getPublishStatus(publishId) {
    const token = await this.getAccessToken();
    const response = await axios.post(
      `https://api.weixin.qq.com/cgi-bin/freepublish/get?access_token=${token}`,
      { publish_id: publishId },
      { timeout: 30000 }
    );
    if (response.data?.errcode && response.data.errcode !== 0) {
      throw new Error(response.data.errmsg || "查询发布状态失败");
    }
    return response.data;
  }
}

export default WeChatAPI;
