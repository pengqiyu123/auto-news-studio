import type { ReferenceProject } from "../../types";
import { RefreshBadge } from "../../components/StatusBadge";

export function ReferenceProjectsPanel({ items }: { items: ReferenceProject[] }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">参考项目</p>
          <h2>上游仓库基线与本地状态</h2>
        </div>
      </div>
      <div className="reference-list">
        {items.map((item) => (
          <article key={item.local_name} className="reference-card">
            <div className="row-with-badge">
              <div>
                <strong>{item.local_name}</strong>
                <p>{item.upstream_repo} · {item.branch}</p>
              </div>
              <RefreshBadge status={item.refresh_status} />
            </div>
            <p>层级：{item.layer} · 标签：{item.tags.join(" / ")}</p>
            <p>许可：{item.license_name} · 借鉴方式：{item.borrow_mode}</p>
            <p>借鉴目标：{item.borrow_targets.join(" / ")}</p>
            <p>SHA：{item.commit_sha ?? "暂无"}</p>
            {item.notes ? <span className="warning-note">{item.notes}</span> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
