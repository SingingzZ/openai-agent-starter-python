import type React from 'react';
import styles from './CodeViewer.module.css';

/* ── Token factory ── */
const token = (cls: string) =>
  function Token({ t }: { t: string }) { return <span className={cls}>{t}</span>; };

const Cmt = token(styles.cmt);
const Kw  = token(styles.kw);
const Fn  = token(styles.fn);
const Ty  = token(styles.ty);
const Str = token(styles.str);
const Op  = token(styles.op);
const Va  = token(styles.va);

interface LineProps { n: number; children?: React.ReactNode }
const L = ({ n, children }: LineProps) => (
  <div className={styles.line}>
    <span className={styles.ln}>{String(n).padStart(2, ' ')}</span>
    <span className={styles.lc}>{children ?? ' '}</span>
  </div>
);

/* Indent helpers */
const I1 = ({ children }: { children?: React.ReactNode }) => (
  <><span className={styles.indent} />{children}</>
);
const I2 = ({ children }: { children?: React.ReactNode }) => (
  <><span className={styles.indent} /><span className={styles.indent} />{children}</>
);

export default function CodeViewer() {
  return (
    <div className={styles.panel}>
      {/* ── Header ── */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.fileIcon}>⬡</span>
          <span className={styles.filename}>agents/chat/index.py</span>
        </div>
        <span className={styles.badge}>READ ONLY</span>
      </div>

      {/* ── Code body ── */}
      <div className={styles.body}>
        {/* CRT scanline overlay */}
        <div className={styles.scanline} aria-hidden />

        <div className={styles.code}>
          {/* ── Imports ── */}
          <L n={1}><Kw t="from " /><Va t="openai" /><Kw t=" import " /><Ty t="AsyncOpenAI" /></L>
          <L n={2}><Kw t="from " /><Va t="agents" /><Kw t=" import " /><Ty t="Agent" /><Op t=", " /><Ty t="OpenAIChatCompletionsModel" /><Op t=", " /><Ty t="Runner" /></L>
          <L n={3}><Kw t="from " /><Va t="._tools" /><Kw t=" import " /><Va t="find_malls_with_shops" /><Op t=", " /><Cmt t="# ..." /></L>
          <L n={4} />

          {/* ── 1. Model ── */}
          <L n={5}><Cmt t="# 1. 接入 AI Gateway 上的大模型" /></L>
          <L n={6}>
            <Va t="llm_model" /><Op t=" = " /><Ty t="OpenAIChatCompletionsModel" /><Op t="(" />
          </L>
          <L n={7}>
            <I1><Va t="model" /><Op t="=" /><Va t="os" /><Op t="." /><Fn t="getenv" /><Op t="(" /><Str t='"AI_GATEWAY_MODEL"' /><Op t=")" /><Op t="," /></I1>
          </L>
          <L n={8}>
            <I1><Va t="openai_client" /><Op t="=" /><Va t="llm_client" /><Op t="," /></I1>
          </L>
          <L n={9}>
            <Op t=")" />
          </L>
          <L n={10} />

          {/* ── 2. Tools ── */}
          <L n={11}><Cmt t="# 2. 工具：全部基于高德地图实时 POI 数据" /></L>
          <L n={12}>
            <Va t="TOOLS" /><Op t=" = [" />
          </L>
          <L n={13}>
            <I1><Fn t="find_malls_with_shops" /><Op t=", " /><Cmt t="# 🎯 同时有 A 和 B 的商场" /></I1>
          </L>
          <L n={14}>
            <I1><Fn t="search_nearby_malls" /><Op t=", " /><Cmt t="# 🏬 附近商场检索" /></I1>
          </L>
          <L n={15}>
            <I1><Fn t="search_shop_nearby" /><Op t=", " /><Cmt t="# 🏷️ 门店检索（带纠错）" /></I1>
          </L>
          <L n={16}>
            <I1><Fn t="plan_route" /><Op t=", " /><Cmt t="# 🧭 路径规划" /></I1>
          </L>
          <L n={17}>
            <I1><Fn t="geocode_location" /><Op t=", " /><Cmt t="# 📍 位置定位" /></I1>
          </L>
          <L n={18}>
            <Op t="]" />
          </L>
          <L n={19} />

          {/* ── 3. Agent ── */}
          <L n={20}>
            <Va t="agent" /><Op t=" = " /><Ty t="Agent" /><Op t="(" />
          </L>
          <L n={21}>
            <I1><Va t="name" /><Op t="=" /><Str t='"出行决策助手"' /><Op t="," /></I1>
          </L>
          <L n={22}>
            <I1><Va t="instructions" /><Op t="=" /><Va t="INSTRUCTIONS" /><Op t="," /></I1>
          </L>
          <L n={23}>
            <I1><Va t="tools" /><Op t="=" /><Va t="TOOLS" /><Op t="," /></I1>
          </L>
          <L n={24}>
            <I1><Va t="model" /><Op t="=" /><Va t="llm_model" /><Op t="," /></I1>
          </L>
          <L n={25}>
            <Op t=")" />
          </L>
          <L n={26} />

          {/* ── 4. Handler ── */}
          <L n={27}><Cmt t="# 3. 入口：EdgeOne Makers 自动映射到 POST /chat" /></L>
          <L n={28}>
            <Kw t="async def " /><Fn t="handler" /><Op t="(" /><Va t="context" /><Op t="):" />
          </L>
          <L n={29}>
            <I1><Va t="message" /><Op t=" = " /><Va t="context" /><Op t="." /><Va t="request" /><Op t="." /><Va t="body" /><Op t="." /><Fn t="get" /><Op t="(" /><Str t='"message"' /><Op t=")" /></I1>
          </L>
          <L n={30}>
            <I1><Va t="session" /><Op t=" = " /><Va t="context" /><Op t="." /><Va t="store" /><Op t="." /><Fn t="openai_session" /><Op t="(" /><Va t="cid" /><Op t=")" /></I1>
          </L>
          <L n={31}>
            <I1><Va t="cancel_signal" /><Op t=" = " /><Va t="context" /><Op t="." /><Va t="request" /><Op t="." /><Va t="signal" /></I1>
          </L>
          <L n={32} />

          {/* ── 5. Stream ── */}
          <L n={33}>
            <I1><Va t="result" /><Op t=" = " /><Ty t="Runner" /><Op t="." /><Fn t="run_streamed" /><Op t="(" /><Va t="agent" /><Op t=", " /><Va t="input" /><Op t="=" /><Va t="message" /><Op t=", " /><Va t="session" /><Op t="=" /><Va t="session" /><Op t=")" /></I1>
          </L>
          <L n={34}>
            <I1><Kw t="async for " /><Va t="event" /><Kw t=" in " /><Va t="result" /><Op t="." /><Fn t="stream_events" /><Op t="():" /></I1>
          </L>
          <L n={35}>
            <I2><Kw t="if " /><Va t="cancel_signal" /><Op t="." /><Fn t="is_set" /><Op t="(): " /><Kw t="break" /><Cmt t="  # 用户点了停止" /></I2>
          </L>
          <L n={36} />
          <L n={37}>
            <I2><Cmt t="# 逐 token 推送到前端聊天窗口" /></I2>
          </L>
          <L n={38}>
            <I2><Kw t="yield " /><Fn t="sse" /><Op t="(" /><Str t='"text_delta"' /><Op t=", " /><Op t="{" /><Str t='"delta"' /><Op t=": " /><Va t="event" /><Op t="." /><Va t="data" /><Op t="." /><Va t="delta" /><Op t="})" /></I2>
          </L>
          <L n={39}>
            <I2><Kw t="yield " /><Fn t="sse" /><Op t="(" /><Str t='"tool_called"' /><Op t=", " /><Op t="{" /><Str t='"tool"' /><Op t=": " /><Va t="tool_name" /><Op t="})" /></I2>
          </L>
        </div>
      </div>

      {/* ── Footer tag ── */}
      <div className={styles.footer}>
        <span className={styles.footerDot} />
        <span>OpenAI Agents SDK · 高德地图 · EdgeOne Makers</span>
      </div>
    </div>
  );
}
