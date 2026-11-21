import { useState } from "react";
import Dialog from "./Dialog";
import Select from "./Select";
import { Input } from "./fields";
import { Icon } from "./ui";

const engines = {
  bing: ["必应", "https://www.bing.com/search", "q"],
  baidu: ["百度", "https://www.baidu.com/s", "wd"],
  google: ["Google", "https://www.google.com/search", "q"],
} as const;

export default function ResourceSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [engine, setEngine] = useState<keyof typeof engines>("bing");
  const selected = engines[engine];
  const url = new URL(selected[1]);
  url.searchParams.set(selected[2], query.trim());
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        <Icon name="search" />
        联网查资料
      </button>
      {open && (
        <Dialog title="联网查资料" onClose={() => setOpen(false)}>
          <p className="muted">
            在新标签页搜索公开资料。找到合适的文件后，可下载并上传到资料库。
          </p>
          <div className="form-field">
            <label htmlFor="resource-search-query">搜索关键词</label>
            <Input
              id="resource-search-query"
              type="search"
              placeholder="例如：微积分 入门 教材 PDF"
              maxLength={200}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <div className="form-field">
            <label htmlFor="resource-search-engine">搜索引擎</label>
            <Select
              id="resource-search-engine"
              label="搜索引擎"
              value={engine}
              onChange={setEngine}
              options={Object.entries(engines).map(([value, [label]]) => ({
                value: value as keyof typeof engines,
                label,
              }))}
            />
          </div>
          <p className="muted small">
            仅将你填写的关键词发送到所选搜索引擎，不会附带学习记录、资料或 API
            Key。搜索结果由第三方提供。
          </p>
          <div className="content-actions form-footer">
            <button type="button" onClick={() => setOpen(false)}>
              取消
            </button>
            {query.trim() ? (
              <a
                className="button primary"
                href={url.href}
                target="_blank"
                rel="noopener noreferrer"
              >
                搜索资料 <span aria-hidden="true">↗</span>
              </a>
            ) : (
              <button className="primary" disabled>
                搜索资料
              </button>
            )}
          </div>
        </Dialog>
      )}
    </>
  );
}
