import {
  Bold,
  Code,
  Heading1,
  Heading2,
  Heading3,
  Image,
  Italic,
  Link,
  List,
  ListOrdered,
  Minus,
  Quote,
  Redo2,
  Undo2,
  X,
  Eye,
  EyeOff,
  Save,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import CharacterCount from "@tiptap/extension-character-count";
import ImageExtension from "@tiptap/extension-image";
import LinkExtension from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";
import { EditorContent, useEditor } from "@tiptap/react";

import { api } from "../lib/api";
import type { DraftItem, PipelineStage } from "../types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getEditorMarkdown(ed: any): string {
  if (!ed) return "";
  return (ed.storage as Record<string, { getMarkdown: () => string }>).markdown.getMarkdown();
}

interface DraftEditorModalProps {
  draft: DraftItem;
  onClose: () => void;
  onSave: (draftId: string, updated: DraftItem) => void;
}

const STAGE_LABELS: Record<PipelineStage, string> = {
  collected: "已采集",
  curated: "已筛选",
  drafted: "已生成",
  draft_synced: "已进草稿箱",
  preview_ready: "预览就绪",
  approved: "已审核",
  published: "已发布",
  failed: "失败",
};

export function DraftEditorModal({ draft, onClose, onSave }: DraftEditorModalProps) {
  const [title, setTitle] = useState(draft.title);
  const [showPreview, setShowPreview] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "dirty">("saved");
  const [previewHtml, setPreviewHtml] = useState(draft.wechat_html);
  const isDirty = useRef(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const titleRef = useRef(title);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
      ImageExtension.configure({ inline: false, allowBase64: true }),
      LinkExtension.configure({ openOnClick: true, HTMLAttributes: { target: "_blank" } }),
      Placeholder.configure({ placeholder: "开始撰写..." }),
      CharacterCount,
      Markdown.configure({ html: false, transformPastedText: true, transformCopiedText: true }),
    ],
    content: draft.markdown,
    onUpdate: ({ editor: ed }) => {
      isDirty.current = true;
      setSaveStatus("dirty");
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        void doSave(ed);
      }, 2000);
    },
  });

  titleRef.current = title;

  const doSave = useCallback(
    async (ed: typeof editor | null) => {
      if (!ed) return;
      const md = getEditorMarkdown(ed);
      setSaveStatus("saving");
      try {
        const result = await api.updateDraftContent(draft.id, { markdown: md, title: titleRef.current });
        setPreviewHtml(result.item.wechat_html);
        onSave(draft.id, result.item);
        isDirty.current = false;
        setSaveStatus("saved");
      } catch {
        setSaveStatus("dirty");
      }
    },
    [draft.id, onSave],
  );

  const handleManualSave = useCallback(() => {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    void doSave(editor);
  }, [editor, doSave]);

  const handleClose = useCallback(() => {
    if (isDirty.current) {
      if (!confirm("稿件尚未保存，确定关闭？")) return;
    }
    onClose();
  }, [onClose]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "s") {
        e.preventDefault();
        handleManualSave();
      } else if (e.ctrlKey && e.key === "p") {
        e.preventDefault();
        setShowPreview((prev) => !prev);
      } else if (e.key === "Escape") {
        e.preventDefault();
        handleClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleManualSave, handleClose]);

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  const handleImageUpload = useCallback(async () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file || !editor) return;
      try {
        const { url } = await api.uploadImage(file);
        editor.chain().focus().setImage({ src: url }).run();
      } catch {
        // upload failed silently
      }
    };
    input.click();
  }, [editor]);

  const handleLinkInsert = useCallback(() => {
    if (!editor) return;
    const url = prompt("输入链接地址:");
    if (url) {
      editor.chain().focus().setLink({ href: url }).run();
    }
  }, [editor]);

  if (!editor) return null;

  const charCount = editor.storage.characterCount.characters();
  const wordCount = editor.storage.characterCount.words();
  const readingMin = Math.max(1, Math.ceil(charCount / 400));

  const SAVE_LABEL: Record<string, string> = {
    saved: "已保存",
    saving: "保存中...",
    dirty: "未保存",
  };

  const toolbarButtons = [
    { icon: Bold, action: () => editor.chain().focus().toggleBold().run(), isActive: () => editor.isActive("bold"), label: "加粗" },
    { icon: Italic, action: () => editor.chain().focus().toggleItalic().run(), isActive: () => editor.isActive("italic"), label: "斜体" },
    { icon: Code, action: () => editor.chain().focus().toggleCode().run(), isActive: () => editor.isActive("code"), label: "代码" },
    { type: "divider" as const },
    { icon: Heading1, action: () => editor.chain().focus().toggleHeading({ level: 1 }).run(), isActive: () => editor.isActive("heading", { level: 1 }), label: "标题1" },
    { icon: Heading2, action: () => editor.chain().focus().toggleHeading({ level: 2 }).run(), isActive: () => editor.isActive("heading", { level: 2 }), label: "标题2" },
    { icon: Heading3, action: () => editor.chain().focus().toggleHeading({ level: 3 }).run(), isActive: () => editor.isActive("heading", { level: 3 }), label: "标题3" },
    { type: "divider" as const },
    { icon: List, action: () => editor.chain().focus().toggleBulletList().run(), isActive: () => editor.isActive("bulletList"), label: "无序列表" },
    { icon: ListOrdered, action: () => editor.chain().focus().toggleOrderedList().run(), isActive: () => editor.isActive("orderedList"), label: "有序列表" },
    { icon: Quote, action: () => editor.chain().focus().toggleBlockquote().run(), isActive: () => editor.isActive("blockquote"), label: "引用" },
    { type: "divider" as const },
    { icon: Minus, action: () => editor.chain().focus().setHorizontalRule().run(), isActive: () => false, label: "分割线" },
    { icon: Link, action: handleLinkInsert, isActive: () => editor.isActive("link"), label: "链接" },
    { icon: Image, action: handleImageUpload, isActive: () => false, label: "图片" },
    { type: "divider" as const },
    { icon: Undo2, action: () => editor.chain().focus().undo().run(), isActive: () => false, label: "撤销" },
    { icon: Redo2, action: () => editor.chain().focus().redo().run(), isActive: () => false, label: "重做" },
  ];

  return createPortal(
    <div className="editor-overlay" onClick={handleClose}>
      <div className="editor-container" onClick={(e) => e.stopPropagation()}>
        <div className="editor-header">
          <div className="editor-header-left">
            <input
              className="editor-title-input"
              value={title}
              onChange={(e) => { setTitle(e.target.value); isDirty.current = true; setSaveStatus("dirty"); }}
              placeholder="输入文章标题..."
            />
            <span className="status-badge status-neutral">{STAGE_LABELS[draft.pipeline_stage]}</span>
          </div>
          <div className="editor-header-actions">
            <button type="button" className="ghost-button compact" onClick={() => setShowPreview((prev) => !prev)} title="Ctrl+P 切换预览">
              {showPreview ? <EyeOff size={14} /> : <Eye size={14} />}
              {showPreview ? "隐藏预览" : "显示预览"}
            </button>
            <button type="button" className="primary-button compact" onClick={handleManualSave} disabled={saveStatus === "saving"}>
              <Save size={14} />
              {saveStatus === "saving" ? "保存中..." : "保存"}
            </button>
            <button type="button" className="ghost-button compact" onClick={handleClose} title="Esc 关闭">
              <X size={14} />
            </button>
          </div>
        </div>

        <div className="editor-toolbar">
          {toolbarButtons.map((btn, i) => {
            if ("type" in btn && btn.type === "divider") {
              return <div key={i} className="editor-toolbar-divider" />;
            }
            const Icon = btn.icon;
            return (
              <button
                key={i}
                type="button"
                className={btn.isActive() ? "is-active" : ""}
                onClick={btn.action}
                title={btn.label}
              >
                <Icon size={15} />
              </button>
            );
          })}
        </div>

        <div className={`editor-split ${showPreview ? "" : "editor-only"}`}>
          <div className="editor-pane">
            <div className="editor-pane-label">编辑</div>
            <div className="editor-pane-content">
              <EditorContent editor={editor} />
            </div>
          </div>
          {showPreview && (
            <div className="editor-pane">
              <div className="editor-pane-label">微信预览</div>
              <div className="editor-pane-content">
                <div className="wechat-preview-container" dangerouslySetInnerHTML={{ __html: previewHtml }} />
              </div>
            </div>
          )}
        </div>

        <div className="editor-status-bar">
          <div className="editor-status-left">
            <span>{wordCount} 字</span>
            <span>约 {readingMin} 分钟阅读</span>
          </div>
          <div className="editor-status-right">
            <span>
              <span className={`editor-save-dot ${saveStatus}`} />
              {SAVE_LABEL[saveStatus]}
            </span>
            <span style={{ color: "#94a3b8" }}>Ctrl+S 保存 / Ctrl+P 预览 / Esc 关闭</span>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
