# 智能体配置指南 — Orchestrator Agent Configuration

本文档定义调用 wechat-article-writer 技能的**编排智能体（Orchestrator Agent）**的最佳配置。安装技能后，按此指南配置智能体，实现现行主链下的自动化执行与必要人工配合。

---

## 一、核心原则

- **能自动跑的步骤不问人**（调研、初稿、评审、改稿、排版适配、发布准备）
- **必须停下来等人的步骤明确标注**（扫码 / 登录 / boss 确认等真实阻塞）
- **语音消息是主要反馈方式** — 智能体必须能处理语音转文字并据此行动
- **状态持久化** — 所有进度写入 `pipeline-state.json`，不依赖会话记忆
- **当前通过线单一且明确** — Reviewer 只看 `weighted_total`；具体通过门槛数字只认 `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/config.json` 里的 `review_pass_threshold`。严重问题通过评分与 `critical_issues` 表达，不另设 blocker gate

---

## 二、Gateway 配置

```yaml
# openclaw config 关键字段
session:
  idleMinutes: 10080        # 7天空闲才重置（文章流程可能跨多天）
  
defaultModel: anthropic/claude-sonnet-4-5   # 日常对话和评审用Sonnet（省钱）
```

**模型策略：**
| 任务 | 模型 | 原因 |
|------|------|------|
| 日常对话、评审 | Sonnet (默认) | 成本低，评审质量够用 |
| 初稿写作、改稿 | 默认继承主会话模型；`writer_model` 仅作可选覆盖 | Writer 与其他子环节一样，统一走认证后的主模型子代理路径 |

---

## 三、AGENTS.md 追加规则

将以下内容追加到编排智能体的 `AGENTS.md`：

```markdown
## 微信公众号文章写作规则

### 自动执行（不问人）
- **主 agent 先做热点预扫，再定题**（优先使用个人 skill `jj-search-stack`；其内部已定义 URL 编码规范、`web_search` 边界、白名单入口：搜狗微信 / 搜狗网页 / DuckDuckGo HTML / Startpage / Brave Search → `web_fetch` 抽取验证；`tavily-search` 作为稳定增强与兜底；避免 Bing 搜索页、东方财富搜索页）
- 撰写大纲
- 生成初稿（spawn Writer 子代理；默认直接继承主会话模型；只有在 `config.json.writer_model` 显式非空时才覆盖 Writer 模型；仍保持 Writer child 边界与产物契约不变）
- 评审打分（spawn Reviewer 子代理，用 Sonnet 模型）
- 自动修改循环（最多 2 轮；第 2 次仍不过线就从 fresh first-draft branch 重开，不沿旧稿硬磨）
- Layout 渲染适配（render adapter：可做结构扫描、重点锚点与微信安全排版；不得改 thesis / facts / arguments / voice；输入必须是 Reviewer-approved draft）
- 发布到草稿箱 / 正式发布链路（按当前 publish 合同执行）

### 必须等人确认
- **用户明确给了人工修订方向**：优先按用户要求改，不和自动评分硬顶
- **发布链路出现真实人工门**：如登录扫码 / safe_check / boss_confirm，暂停并等用户完成

### 用户反馈处理
- 用户可能通过**语音消息**给反馈 — 直接根据转录文字行动
- 用户说"改一下XX" → 直接改，不要确认
- 用户说"不好"/"重写" → 回到步骤4重写
- 用户说"可以了" → 进入下一步
- 用户沉默超过60分钟 → 发一条提醒，不要反复催

### 权限边界
- 主 agent：第一选题权
- Orchestrator：流程权，不改题
- Researcher：验证权 + 有限纠偏权
- Writer：拥有正文文风和真人化表达责任
- Reviewer：唯一内容质量裁判；Voice 不达标就退回 Writer
- Layout：render adapter，可做语义保持型结构与微信端适配；不得改 thesis / facts / arguments / voice

### Pipeline 状态
- 每个主要步骤完成后更新 pipeline-state.json
- 只有用户明确给出 `draft_id` / 明确要求继续时才按旧 pipeline-state 恢复进度
- 对 scheduled daily cron，默认 fresh run，新建 slug，不要接管旧 failed 草稿
- 不要依赖会话记忆来跟踪进度
```

---

## 四、HEARTBEAT.md 追加规则

```markdown
## 文章 Pipeline 检查
每次心跳检查 /root/.openclaw/workspace-xiaolongxia/wechat-article-writer/drafts/*/pipeline-state.json
- 如果有 phase 不是 "done" 且不是等待人工的阶段 → 继续执行
- 如果 phase 是 "awaiting_human" → 不要自动继续，等用户
- 如果 pipeline 超过 24 小时没更新 → 提醒用户
```

---

## 五、SOUL.md 建议追加

```markdown
## 文章写作人格
写文章时切换到"编辑"模式：
- 对文字质量极其严格，不放过任何教材腔/翻译腔/鸡汤腔
- 但对用户反馈高度响应 — 用户说改就改，不要辩解
- 主动提供改进建议，但不强制执行
- 如果用户的意见和评审冲突，以用户意见为准
```

---

## 六、技能依赖清单

安装 wechat-article-writer 前，确保以下技能已安装：

```bash
# 必须
openclaw skill install wechat-mp-publisher   # 发布到草稿箱

# 推荐
openclaw skill install openai-whisper-api    # 语音转文字（处理用户语音反馈）
```

---

## 七、完整安装检查清单

| # | 检查项 | 命令 |
|---|--------|------|
| 1 | wechat-mp-publisher 已安装 | `which mcporter` |
| 2 | MCP 配置已就绪 | `cat ~/.openclaw/mcp.json` |
| 3 | session idle >= 7天 | 检查 OpenClaw gateway 配置 |
| 4 | 默认模型 Sonnet | `openclaw status` |
| 5 | 语音转文字可用 | openai-whisper-api 技能已安装 |

---

## 十、Cron 错误监控

**Cron job 失败是静默的** — 不会主动通知任何人。必须通过以下方式监控：

1. **HEARTBEAT.md 中添加 cron 健康检查**（setup.sh 已自动添加）
2. **Discord delivery target 必须使用 `channel:` 前缀**（e.g. `channel:1234567890`），否则报 "Ambiguous Discord recipient" 并静默失败
3. 如果 `consecutiveErrors >= 2`，禁用该 job 并通知用户

> **注意：** 旧版文档提到 `setup.sh` 会自动添加 HEARTBEAT 规则。该脚本已移除，请手动将上方 HEARTBEAT.md 规则追加到你的配置中。

## 十一、常见问题

**Q: 文章流程跑到一半，会话被重置了怎么办？**
A: pipeline-state.json 保存了完整状态。新会话启动后，心跳检查会发现未完成的 pipeline 并恢复。

**Q: 评审分数始终达不到通过线怎么办？**
A: 现行通过线数字不再写死在文档里；唯一权威源是 `config.json.review_pass_threshold`。自动 revise 最多 2 轮；如果第 2 次后仍未过线，就从 fresh first-draft branch 重开。用户的判断优先于自动评分，不要在旧稿上无限硬磨。

**Q: wenyan 输出乱码？**
A: wenyan 输出缺少 `<meta charset="utf-8">`，步骤8会自动注入。如果直接打开 raw.html 会乱码，这是正常的。
