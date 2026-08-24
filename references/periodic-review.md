# 定期复盘（默认每周一上午 10:30）

让领导力提升不靠"想起来才做"，而是每周固定复盘上一周的真实表现。本 skill 不自带常驻进程；排期存在私有状态里，由宿主 agent 的定时/自动化能力触发。

## 排期约定

默认：**每周一 10:30 · Asia/Shanghai · 复盘上一自然周**。存在私有状态 `schedule`：

```bash
python3 scripts/state.py init --report-time 10:30 --timezone Asia/Shanghai --weekday mon
```

`--weekday` 可选（`mon`..`sun`），只作为给宿主排期器的元信息，不影响时间窗计算。用户想改成别的节奏（如每周五收尾、双周），改这里即可。

## 怎么触发（各 agent 自己的排期能力）

本 skill 只声明"该在什么时候跑"，真正的定时交给宿主：

- **Codex/桌面版**：用 automation/reminder 能力建一个"每周一 10:30 运行 leadership-coach 定期复盘"的循环任务。
- **有 cron 的环境**：`crontab` 里 `30 10 * * 1` 触发一次调用本 skill 的命令。
- **无排期能力**：用户每周一手动说"跑一下这周的领导力复盘"，效果相同。

排期器只负责"叫醒"，所有分析仍在本 skill 内、`--as user` 只读完成。

## 定期复盘模式与首次运行的差异

| 环节 | 首次 / 按需 | 定期复盘 |
|---|---|---|
| 阶段 1 多轮对齐 | 完整走，建立契约 | **跳过**（状态里已有确认的方向/阶段） |
| 时间窗 | 近 30 天 | **上一周**：`state.py window` 从 `last_success_at` 起算到本次 |
| 诊断范围 | 建立基线 | 只诊断上周新增证据 + 与上次"最该改的一件事"对比 |
| 收尾 | 落报告 | 落报告 + `state.py mark-success` 推进检查点、存指纹 |

若状态里 `intent.confirmed=false`（从没对齐过），定期模式要先退回阶段 1 做一次对齐，不能凭空复盘。

## 增量与去重

- `state.py window` 给出 `[last_success_at, now]` 的时间窗；只取落在窗内的会议/沟通。
- 每场会议逐字用 `state.py fingerprint --source meeting` 生成 `source:sha256` 指纹；已在 `scan.fingerprints` 里的跳过，避免上周分析过的会这周又算一遍。
- 成功后 `state.py mark-success --at <now-RFC3339>`，stdin 传本周新指纹，推进 `last_success_at`。

## 定期报告的额外一节：趋势对比

除标准诊断结构外，定期报告开头加一句**趋势判断**：上次"最该改的一件事"这周有没有改善？给证据（如"上周开场独白 252 字→本周 90 字，且先抛了一个开放问题"）。这是定期复盘相对单次诊断的核心增量价值——让用户看见自己在动。