import { useEffect, useRef } from 'react';
import type { RawSseEvent } from '../api';
import { useT } from '../i18n';
import styles from './DebugPanel.module.css';

interface Props {
  events: RawSseEvent[];
  onClear: () => void;
  /** Collapsed = only the status bar is visible; body is unmounted. */
  collapsed: boolean;
  onToggle: () => void;
  /** True while a request is streaming, used to light up the status dot. */
  streaming: boolean;
}

export default function DebugPanel({ events, onClear, collapsed, onToggle, streaming }: Props) {
  const { t, lang } = useT();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to newest — only meaningful while the body is mounted.
  useEffect(() => {
    if (collapsed) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events, collapsed]);

  return (
    <div className={`${styles.panel} ${collapsed ? styles.collapsed : styles.expanded}`}>
      <button
        type="button"
        className={styles.header}
        onClick={onToggle}
        aria-expanded={!collapsed}
        title={collapsed ? t('debug.expand') : t('debug.collapse')}
      >
        <span className={`${styles.chevron} ${collapsed ? '' : styles.chevronOpen}`}>›</span>

        <span className={styles.headerLeft}>
          <span className={`${styles.dot} ${streaming ? styles.dotLive : styles.dotIdle}`} />
          <span className={styles.title}>{t('debug.title')}</span>
          <span className={styles.count}>{events.length} {t('debug.events')}</span>
          {streaming && <span className={styles.live}>{t('debug.live')}</span>}
        </span>

        <span className={styles.hint}>{collapsed ? t('debug.expand') : t('debug.collapse')}</span>
      </button>

      {!collapsed && (
        <div className={styles.bodyWrap}>
          <span
            className={styles.clearBtn}
            role="button"
            tabIndex={0}
            onClick={(e) => { e.stopPropagation(); onClear(); }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                e.stopPropagation();
                onClear();
              }
            }}
          >
            {t('debug.clear')}
          </span>

          <div className={styles.body} ref={scrollRef}>
            {events.length === 0 && (
              <div className={styles.empty}>
                {t('debug.empty')}<br />
                {t('debug.emptyHint')}
              </div>
            )}

            {events.map((evt, i) => (
              <div key={`${evt.timestamp}-${i}`} className={styles.event}>
                <div className={styles.eventHeader}>
                  <span className={`${styles.eventType} ${styles[`type_${evt.eventType}`] || styles.type_unknown}`}>
                    {evt.eventType}
                  </span>
                  <span className={styles.eventTime}>
                    {new Date(evt.timestamp).toLocaleTimeString(lang === 'zh' ? 'zh-CN' : 'en-US', {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                </div>
                <pre className={styles.eventData}>
                  {evt.data !== null && typeof evt.data === 'object'
                    ? JSON.stringify(evt.data, null, 2)
                    : evt.raw}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
