const en = {
  // Header
  "app.title": "Trip Decision Assistant",
  "app.subtitle": "Tell me where you are, I'll find the mall worth going to",

  // Empty state
  "empty.title": "Trip Decision Assistant",
  "empty.hint": "Tell me your location and the shops you want. I search live AMap POI data to find the nearest mall that has all of them, with distance, travel time and floor info.",
  "empty.features": "AMap POI · Typo Correction · Route Planning",

  // Chat input
  "chat.placeholder": "Type a message...  ⏎ Send · Shift+⏎ Newline",
  "chat.hint": "Powered by OpenAI Agents SDK + EdgeOne Makers · Data from AMap",

  // Preset questions
  "preset.1": "I'm near Honglian South Road metro station. Find me a nearby mall that has both Breo and Xiting Cunwu.",
  "preset.2": "I'm at Shenzhen North Railway Station. Which malls are nearby and how do I get there by metro?",

  // Tool indicators
  "tool.recommend": "Recommend",
  "tool.malls": "Find Malls",
  "tool.shops": "Find Shops",
  "tool.route": "Route",
  "tool.locate": "Locate",

  // Status & errors
  "status.error": "Request failed. Please check if the backend service is running.",
  "status.stopped": "⏹ *Generation stopped*",
  "status.backendError": "Backend abort request failed. The server may still be running.",

  // Debug panel
  "debug.title": "Trace",
  "debug.events": "events",
  "debug.clear": "Clear",
  "debug.empty": "Waiting for SSE events...",
  "debug.emptyHint": "After sending a message, all raw backend data will be displayed here.",
  "debug.expand": "Expand",
  "debug.collapse": "Collapse",
  "debug.live": "LIVE",

  // Conversation sidebar
  "sidebar.label": "Conversation list",
  "sidebar.title": "Chats",
  "sidebar.newChat": "New chat",
  "sidebar.loading": "Loading conversations...",
  "sidebar.loadMore": "Load more",
  "sidebar.loadingMore": "Loading...",
  "sidebar.emptyTitle": "No conversations yet",
  "sidebar.emptyHint": "Click \"New chat\" to start your first conversation.",
  "sidebar.delete": "Delete conversation",
  "sidebar.deleteConfirm": "Permanently delete this conversation? This cannot be undone.",

  // Aria labels (button hover/screen-reader)
  "aria.send": "Send",
  "aria.clearHistory": "Clear history",
  "aria.stopGeneration": "Stop generation",

  // Language toggle
  "lang.switch": "中文",

  // ─── Floating bottom-right action badges ─────────────────────────────
  "floatingLink.deploy": "Deploy",
  "floatingLink.github": "GitHub",
} as const;

export default en;
