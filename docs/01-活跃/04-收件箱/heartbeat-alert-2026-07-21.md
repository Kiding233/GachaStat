# heartbeat-alert-2026-07-21

> C6 heartbeat-monitor | 2026-07-21

## 告警

| Agent | 最后心跳 | 阈值 | 状态 |
|-------|---------|------|------|
| **C3** weekly-writer | 814h（~34d） | 48h | 🔴 告警 |
| **C5** quality-reviewer | 813h（~34d） | 48h | 🔴 告警 |
| C6 heartbeat-monitor | 815h（~34d） | — | ⚠️ 自检 |

## 根因

Cron agent 7 天自动过期——自 2026-06-17 以来未重新注册。C1/C2/C4/E1 已于今日手动运行恢复。C3/C5 为周一专属 agent（今日周二），未自动触发。

## 预期恢复

下次周一（2026-07-27）C3/C5 应正常触发。C6 本次运行已恢复。`quality-reviewer.txt` 需在下次 C5 运行时由 C5 自行 touch。
