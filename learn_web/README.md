# Learn Everything 前端

Vite + React + TypeScript，调 `/api/v2`。

```sh
npm install
npm run dev     # 5173，/api/v2 代理到 127.0.0.1:8000
npm run build   # 产出 dist/，线上挂 /official/learn-everything/app/
```

## 门票

官网打开页面时带 `?ticket=xxx`，前端取到后存 sessionStorage 并从地址栏抹掉；
之后每个请求带 `X-Learn-Ticket`。直接访问没有门票时，接口会返回 401。

## 页面

项目列表 → 项目详情（知识节点 / 今日复习 / 资料 / 测验 / 学习路径 / 每日报告）。
