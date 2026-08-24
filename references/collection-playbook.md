# 采集口径与命令 Playbook

按**证据价值排序**采集本人飞书资产。命令 shortcut 以各依赖 skill 的 SKILL.md / `lark-cli <domain> --help` 为准；本文件给口径、顺序与实测过的坑，不硬编码可能过期的 flag。执行前按对应 skill 的渐进式发现规则确认命令存在。

时间窗默认近 30 天（可按需扩到 60–90 天，尤其会议低频时），落到显式区间并在报告首行写明。

## 通用原则

- 默认 `--as user`。读取前核验 `identity=user` 与租户。先 `lark-cli contact +get-user --as user` 拿**本人 open_id 与显示名**，后续多处要显式传。
- **`doctor.py` 的 `ready_for_full_scan:false` 是预期常态**：无 `auth status` 的 CLI 构建拿不到 scope 清单，doctor 无法预判各源权限——会议逐字/OKR 能不能读，**只能在本阶段逐源真跑试探**。别把 `full_scan:false` 当阻断，`ready_for_core_scan:true` 即可开工。
- **只读**：本 skill 不写飞书、不发消息、不改纪要。
- **缺权限先征询**：某类资产 scope 缺失读不到时，告诉用户这是重要信号，问是否 `lark-cli auth login --scope <缺失scope> --as user` 补授权。只读演练/无人值守模式下不阻塞，降级并显著标注"此处本应征询补授权"。
- **默认脱敏**：证据台账只记"来源类型 + 时间 + 本人行为/原话线索"；他人姓名/ID 一律去标识；不落他人评价、薪酬、等级等敏感原文。
- **串行 + 退避**：批量读取易限流，串行调用、失败退避重试。
- 每类资产采完，在证据覆盖报告里记：是否纳入、时间窗、拿到多少条、缺失及原因。

---

## ① 重要会议本人发言（首要证据源）

会议逐字记录里**本人的发言**，是领导风格最真实、最高密度的证据——比零散消息更能看出你怎么设目标、怎么给反馈、怎么处理不同意见、是下指令还是提问题。

1. **定位重要会议**：`lark-vc +search`（`--as user`，带时间窗/关键词/参会人），找周会、评审会、团队会、双周会等**重复性、本人主持或深度参与**的会议。主持/召集的权重高于单纯参加。
2. **取纪要入口**：`lark-vc +detail --meeting-ids <id>` 拿 `note_id`（会议纪要）或 `minute_token`（妙记），按 token 类型路由到 `lark-note` / `lark-minutes` 读**逐字记录 / 原始发言**，而非平台自动总结。
3. **拿逐字稿（实测：是纯文本文件，不是 JSON）**：`lark-cli minutes +detail --minute-tokens <token> --transcript --as user` 会把逐字稿**写到文件**（默认 `./minutes/{minute_token}/transcript.txt`），stdout 只回一个 JSON 元信息、不含正文。文件是纯文本，形如 `说话人 HH:MM:SS.mmm` 头行 + 若干正文行。
4. **转换 → 抽取本人发言（两段管道）**：先用 `transcript_to_json.py` 把纯文本逐字稿转成 JSON，再喂给 `extract_speaker_turns.py`。去标识仍在后者一处完成：

   ```bash
   cat ./minutes/<token>/transcript.txt \
     | python3 scripts/transcript_to_json.py \
     | python3 scripts/extract_speaker_turns.py \
         --me "<你的显示名>"                # 本人显示名，可多次传别名（中英文都传）
         --me-id "ou_xxx"                    # 本人 open_id（可选，更准）
   ```

   `transcript_to_json.py` 跳过标题/关键词等元信息，合并多行发言，输出 `{"sentences":[{"speaker","text"}]}`；`extract_speaker_turns.py` 只保留 `speaker == 本人` 的轮次，**他人全部替换为 `[对方]`**（去标识但保留对话节奏）。若逐字稿本身已是 JSON（个别构建），可跳过转换器直接喂 `extract_speaker_turns.py`。

**实测坑：**
- **`minutes +detail` 的 flag 是 `--minute-tokens`（复数），且 `--transcript` 写文件不打印正文**——别去 stdout 找逐字稿，去 `./minutes/{token}/transcript.txt`（或用 `--output-dir` 指定）。
- 纯文本逐字稿的说话人头行是 `姓名 时:分:秒(.毫秒)`；`transcript_to_json.py` 兼容这种、`[时间] 姓名: 文本`、`姓名：文本` 三种形态。中英文显示名都传给 `--me`（同一人可能同时有中文名和拼音/英文名）。
- `minutes +search` 返回的 `display_info` 是一整段富文本（含 `&lt;b&gt;` 等 HTML 转义），无独立 topic/start_time 字段。取主题切 `display_info` 首行去标签，开始时间从 `meta_data.description` 抠。
- 会议只拿到标题、拿不到逐字记录时，**不能把标题当结论**，标注"仅标题、无逐字记录"。
- **临时文件含真名原文**：`./minutes/` 下的 transcript.txt 是未去标识的原始逐字稿，用完即删，别留在工作区、别提交。

## ② OKR（lark-okr）

看本人如何设目标、纵向对齐、讲进展——目标对齐与决策方向的强信号。

1. `okr +cycle-list` 列周期。**实测强制要 `--user-id <本人 open_id>`**，不带会 validation 报错。
2. 选与时间窗重叠的周期，`okr +cycle-detail` 读 O/KR。
3. 按需 `okr +progress-list` 看进展，`objective.alignments list` 看对齐（承接谁/被谁承接 = 纵向关系）。

**常见坑**：user 身份常缺 `okr:okr.period:readonly`，按通用原则征询补授权。

## ③ 本人发出的关键沟通（lark-im）

只取**本人为 sender**、且带**反馈/决策/指令/承诺/纠偏**语义的消息，围绕用户选定方向的关键词 + 时间窗。

- `im +messages-search --as user --query "<方向关键词>" --start <RFC3339> --end <RFC3339> --no-reactions`，只保留 `sender.id == 本人 open_id`。
- **隐私**：他人回复只用于还原上下文，进入分析前去标识；不存原文，只提炼"本人在此表现出的领导行为"。
- IM 是弱信号层，接口不配合（部分环境 `chat-list` 返回空）时如实标注"信号偏弱"，不强求。

## ④ 本人主编文档（lark-drive / lark-doc）

看本人写的团队复盘、目标拆解、管理沟通、决策文档——反映如何对齐与传达。

- `drive +search --created-by-me --query "<关键词>"`（复盘 / 团队 / 规划 / 目标 / 沟通 / 决策 / 周会纪要）。
- **实测坑（字段路径）**：结果在 `data.results`，标题/时间/owner/token 都在每条的 `result_meta` 子对象（`result_meta.title`、`result_meta.token`、`result_meta.create_time_iso`、`result_meta.owner_name`），顶层同名字段常为 `None`。默认 page-size 15，必须用 `page_token` 翻页后本地按时间窗过滤，别信 `data.total`。
- 命中后 `lark-doc` 读正文（bitable 读不了正文，只取标题或转 `lark-base`）。剔除无语义标题和"同日成批 + 统一前缀"的导入型批量。

## ⑤ 任务（lark-task）

看本人指派/跟进的事项节奏——反映授权与跟进风格。

- `+get-my-tasks` / `+get-related-tasks`（按 `--assignee/--creator/--follower` + 本人 open_id）。
- **实测坑**：任务接口无服务端时间过滤，会返回全量（数百条）。先拉全量再本地按 `created_at >= 窗口起点` 过滤；`created_at` 是 ISO8601 字符串，用 `fromisoformat` 解析，别当毫秒时间戳。
- 提取：分派给谁、是否高频插手细节、是否只派不授权。

---

## 证据覆盖报告

采集结束给一段覆盖说明：每类资产是否纳入、时间窗、拿到多少条证据、哪类缺失及原因（缺权限/未授权/无数据）。让用户知道诊断建立在多少真实数据上、还有哪些重要资产没覆盖——尤其**会议逐字记录没拿到时必须显著提示**，因为它是首要证据源，缺了诊断会明显变弱。
