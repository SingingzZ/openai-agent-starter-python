const zh = {
  // Header
  "app.title": "出行决策助手",
  "app.subtitle": "🌾 告诉我你在哪，帮你找出最值得去的商场",

  // Empty state
  "empty.title": "✦ 出行农场开张啦 ✦",
  "empty.hint": "告诉我你现在的位置和想逛的店，我会基于高德地图的实时数据，找出同时满足要求、离你最近的商场，并给出距离、耗时与店铺楼层。",
  "empty.features": "🗺️ 高德 POI · ✏️ 错别字纠错 · 🧭 路径规划",

  // Chat input
  "chat.placeholder": "🌱 种下你的问题…  ⏎ 发送 · Shift+⏎ 换行",
  "chat.hint": "由 OpenAI Agents SDK + EdgeOne Makers 驱动 · 数据来自高德地图",

  // Preset questions
  "preset.1": "我在红莲南路地铁站附近，想去一个既有倍轻松又有西厅村屋的离得近的商场，帮我推荐。",
  "preset.2": "我在深圳北站，附近有哪些商场可以逛？坐地铁过去怎么走？",

  // Tool indicators
  "tool.recommend": "商场推荐",
  "tool.malls": "商场检索",
  "tool.shops": "门店检索",
  "tool.route": "路线规划",
  "tool.locate": "位置定位",

  // Status & errors
  "status.error": "⚠️ 请求失败，请检查后端服务是否启动。",
  "status.stopped": "⏹ *已停止生成*",
  "status.backendError": "⚠️ 后端中断请求失败，服务端可能仍在运行。",

  // Debug panel
  "debug.title": "传输流",
  "debug.events": "事件",
  "debug.clear": "清除",
  "debug.empty": "等待 SSE 事件...",
  "debug.emptyHint": "发送消息后，所有原始后端数据将在此处显示。",
  "debug.expand": "展开",
  "debug.collapse": "收起",
  "debug.live": "实时",

  // Conversation sidebar
  "sidebar.label": "会话列表",
  "sidebar.title": "会话",
  "sidebar.newChat": "新建聊天",
  "sidebar.loading": "正在加载会话...",
  "sidebar.loadMore": "加载更多",
  "sidebar.loadingMore": "加载中...",
  "sidebar.emptyTitle": "暂无会话",
  "sidebar.emptyHint": "点击「新建聊天」开始第一段对话。",
  "sidebar.delete": "删除会话",
  "sidebar.deleteConfirm": "确定要永久删除这个会话吗？此操作不可恢复。",

  // Aria labels (button hover/screen-reader)
  "aria.send": "发送",
  "aria.clearHistory": "清除历史",
  "aria.stopGeneration": "停止生成",

  // Language toggle
  "lang.switch": "English",

  // ─── Floating bottom-right action badges ─────────────────────────────
  "floatingLink.deploy": "一键部署",
  "floatingLink.github": "GitHub",
} as const;

export default zh;
