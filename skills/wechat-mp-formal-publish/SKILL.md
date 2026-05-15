---
name: wechat-mp-formal-publish
description: 正式把微信公众号草稿箱文章发表出去的技能。凡是用户提到"正式发表公众号文章""把草稿发出去""群发这篇文章""发布到读者端""继续发表""继续群发""审核中""公众号后台扫码验证""微信验证二维码""把草稿箱里的文章真正发出去"时,都应优先使用这个 skill。它处理的是微信公众平台后台里的最终发表动作,不是写稿,也不是通过 WenYan/MCP 创建草稿。
---

# 微信公众号正式发表技能

这个 skill 专门负责 **"草稿已经在公众号后台里了,现在要正式发表/群发出去"** 的最后一段流程。

它和 `wechat-mp-publisher` 的边界要分清:

- `wechat-mp-publisher`:更适合把 Markdown / 素材发布到**草稿箱**。
- `wechat-mp-formal-publish`:更适合从**微信公众平台后台**把现成草稿真正点到"发表/审核中/已发表"。

不要把这两件事混在一起。

## 作为 `wechat-article-forge` 子流程时的额外约束

当本 skill 是被 `wechat-article-forge` 的 Orchestrator / child 流程调用时，规则和主会话直连模式不同：

- **禁止 child 直接 `message` 用户/老板。** 对外转发权归 parent/main agent。
- 命中 `safe_check` / `login_scan` / `boss_confirm` 等人工接力点时，先把二维码或证据文件落到**稳定、非 `/tmp`、按 run 唯一化** 的路径，再把结构化结果返回给上游。
- 推荐稳定路径：`<article-workspace>/media/wechat-safe-check/<sanitized-run-id>/safe-check.png`
- 返回字段至少应包含：`status=need_user_action`、`waiting_for`、`required_user_action`、`safe_check_qr_path`、`relay_status`、`relay_dedupe_key`、`boss_notified_at`、`qr_updated_at`、`blocking_since`、`timeout_at`、`resume_context`。
- 子流程只负责把这些字段返回给上游；由上游调用 `mark_publish_blocked.py` 持久化控制面，并决定何时真正转发给老板。
- 若上游已经显式解析出 `profile` / `mcp_config_file`，本 skill 只能沿用该上下文；禁止自行猜默认 profile 或 fallback 到别的账号配置。

如果当前调用者本身就是面向用户的主 agent，才按下文的“直接发码给当前对话”处理。

## 何时触发

出现以下语义时,直接用本 skill:

- "把草稿箱里的文章发出去"
- "正式发表这篇公众号文章"
- "继续发表 / 继续群发"
- "后台已经有草稿了,你帮我发"
- "现在卡在微信验证 / 安全验证 / 扫码确认"
- "发布后显示审核中没有?"

如果用户要的是:

- 写文章
- 改标题/摘要/排版
- 从 Markdown 创建草稿

那不是本 skill 的主职责。

## 工具优先级

## 本机加固规则（2026-04-08 起强制）

在这台机器上，微信公众号正式发表前，必须先做 **browser-use profile owner preflight**。真实事故已经证明：不同 session 名的 browser-use daemon 仍可能共享同一个 `user_data_dir`，导致扫码写进错误 Chromium，会话之间互相打架。

当前本机约定：

- registry：`${HERMES_SKILL_DIR}/references/browser-use-agent-profiles.json`
- wrapper：`${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh`
- guard：`python3 ${HERMES_SKILL_DIR}/scripts/browser_use_profile_guard.py --agent xiaolongxia --json`

按公众号选择 browser-use agent id：

- 《小龙虾有话说》→ `xiaolongxia`
- 《不上班也有Money》→ `money`

对于正式微信发布：

- **不要再直接裸跑** `browser-use --session ...`
- 优先改用：`${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> ...`
- 在任何登录检查、二维码、发表动作前，先跑 guard
- 如果 guard 报告 `conflicting_sessions` 或 `orphan_holders` 非空：**立刻 fail-closed**，先清理冲突会话，再继续

这条规则优先级高于历史经验里的“直接复用 default 会话”。只有确认 profile owner 正确，复用才安全。

### 首选:`browser-use`

⚠️ **`agent-browser` 命令已废弃,不可用。** 全部改用 `browser-use` CLI。

优先用 `exec` 调 `browser-use` 操作现成浏览器会话,不要新开浏览器。

### 会话约定

不要手写 session 名。通过 `${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> ...` 读取 `references/browser-use-agent-profiles.json`。

常用检查命令:

```bash
${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh xiaolongxia state
${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh xiaolongxia screenshot /tmp/wechat-check.png
${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh xiaolongxia eval "location.href"
```

## 成功标准

最终不要只看"按钮点下去了"。要看微信后台状态:

- 最好看到文章进入 **审核中** 或 **已发表**。
- 如果跳回首页,检查"近期发表"里是否出现目标文章。
- 不能仅凭弹窗消失就宣布成功。

## 标准工作流

### 1) 先确认当前登录态

先看 `default` 会话是否还活着:

```bash
${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> state
browser-use sessions
```

分支判断:

- 如果已在 `mp.weixin.qq.com/cgi-bin/home...token=...` 或编辑页,继续。
- 如果回到 `https://mp.weixin.qq.com/` 登录页,说明会话过期,要重新扫码登录。

### 2) 如果已掉登录,立刻发新的登录二维码

如果在登录页:

1. 刷新页面,确保二维码是最新的。
2. 截图或直接抓登录二维码图片。
3. **直接在当前对话里发图片**,不要发飞书文档链接。
4. 明确告诉用户"扫完回我一句"。

在这个工作区里,用户已经明确表达了偏好:

- **不要把二维码放飞书文档**
- **直接在对话框发图片**

所以后续都照这个偏好执行。

### 2.1) Feishu 当前对话发二维码的实操规则

这一步不要只写“发图片”,要写清楚**怎么发**。这次真实跑通后,当前环境里最稳的经验是:

1. **优先用 `message` 工具的 `media` 参数**,不要把本地路径塞进 `filePath` / `path` 指望它自动变成图片。
2. 如果你拿到的是一个可访问的二维码 URL(例如微信登录码或 `safe_check` 的绝对 URL),优先直接这样发:

```json
{
  "action": "send",
  "channel": "feishu",
  "media": "https://...",
  "message": "🔐 登录二维码。请现在就扫,扫完回我“扫了”。"
}
```

3. 如果没有稳定的远程 URL,再退到 **`buffer` + `mimeType` + 可选 `filename`** 的方式发图片。
4. **不要把 `filePath` 当成图片发送主路径。** 在当前环境里,这样很容易变成“发出一个路径/附件提示”,而不是用户能直接看到的图片消息。
5. 如果你在**当前同一 Feishu DM** 里已经用 `message(action=send)` 发了二维码媒体,本回合就不要再额外输出一条普通文本回包；要么把提示文字写进 `message.message`,要么发完后只输出 `NO_REPLY`,避免触发已知的 delivery-mirror 重复回显。

### 3) 登录成功后,拿到新 token

登录后,主页 URL 里通常会带新的 `token`:

```text
https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=<TOKEN>
```

从 URL 提取 token,再拼编辑页链接:

```text
https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77&appmsgid=<APPMSGID>&token=<TOKEN>&lang=zh_CN
```

如果用户没有给 `appmsgid`,先从"近期草稿 / 全部草稿"里找到目标文章,再进入编辑页。

### 4) 进入文章编辑页

进入后先确认以下关键元素存在:

- 标题输入框
- `button.mass_send` 或可见"发表"按钮
- 页面里确实是目标文章标题
不要在文章不匹配时继续发表。

> ⚠️ **封面图不要在编辑页检测**：微信公众号草稿通过 wenyan/MCP 推送时已携带封面 URL，但编辑页的封面 DOM 选择器（`.cover_appmsg_thumb` 等）在当前环境下不可靠，会误报「无封面」。自动检测封面状态属于已知误判来源，**禁止在此步骤尝试自动检测或上传封面**。如发表时微信提示「必须插入一张图片」，应立即上报 `need_user_action`，由主 agent 通知老板处理。

### 4.5) 设置创作来源（发表前必须执行）

**每篇文章正式发表前，必须将「创作来源」设置为「内容由AI生成」。** 这是平台 AI 内容声明规范要求，不可跳过。

**操作步骤：**

```js
// 1. 点击创作来源区域打开选项弹窗
document.querySelector('.allow_click_opr.js_claim_source_desc')?.click();
```

```js
// 2. 勾选「内容由AI生成」（等 1 秒后执行）
(() => {
  const labels = document.querySelectorAll('label');
  for (const l of labels) {
    if (l.innerText && l.innerText.includes('内容由AI生成')) {
      const input = l.querySelector('input');
      if (input) { input.click(); return '已勾选：内容由AI生成'; }
    }
  }
  return 'ERROR: 未找到「内容由AI生成」选项';
})()
```

```js
// 3. 点「确认」按钮（等 1 秒后执行）
(() => {
  function isVisible(el) {
    const s = window.getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  const btns = document.querySelectorAll('button');
  for (const b of btns) {
    if (b.innerText.trim() === '确认' && isVisible(b)) {
      b.click(); return '点击了确认';
    }
  }
  return 'ERROR: 未找到确认按钮';
})()
```

```js
// 4. 点弹窗右上角 X 关闭（等 2 秒后执行，此时会弹出微信验证弹窗）
// ⚠️ 必须点右上角 X（pop_closed），不能点「取消」
// 点「取消」= 放弃操作，设置不保存；点「X」= 关闭弹窗，设置已保存
// ℹ️ 若点「确认」后弹窗已自动关闭，找不到 X 按钮返回 ERROR 属正常现象，以 Step 5 验证结果为最终判断标准
(() => {
  function isVisible(el) {
    const s = window.getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  const closeBtn = document.querySelector('button.pop_closed');
  if (closeBtn && isVisible(closeBtn)) {
    closeBtn.click(); return '点击了右上角X，设置已保存';
  }
  return 'ERROR: 未找到右上角X按钮（弹窗可能已自动关闭，以Step5验证结果为准）';
})()
```

```js
// 5. 验证设置是否生效（等 2 秒后执行）
document.querySelector('.js_claim_source_selected')?.innerText.trim()
// 应返回「内容由AI生成」
```

**注意事项：**
- 微信验证弹窗（safe_check）**必须点右上角 X 关闭**，不能点「取消」，否则设置丢失
- 如果创作来源已经是「内容由AI生成」（核实后确认），可跳过重复操作，但必须先验证当前值
- 这是文章元数据设置，不影响正文内容

### 4.6) 声明原创（发表前必须执行）

**每篇文章正式发表前，必须完成原创声明。** 默认目标状态：文字原创 · 作者: 当前公众号作者配置 · 已开启快捷转载。

**操作步骤：**

```js
// 1. 点击原创设置入口（右侧面板「原创→未声明」区域）
document.querySelector('.js_original_apply.js_edit_ori')?.click();
```

```js
// 2. 检查弹窗内当前状态（等 2 秒后执行）
// 预期：声明类型=文字原创、作者=当前公众号作者配置、快捷转载=已开启
// 通常无需修改，直接进入步骤 3
(() => {
  function isVisible(el) {
    const s = window.getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  const dialogs = document.querySelectorAll('.weui-desktop-dialog');
  for (const d of dialogs) {
    if (isVisible(d) && d.innerText.includes('文字原创')) {
      return '弹窗已出现：' + d.innerText.slice(0, 120);
    }
  }
  return 'ERROR: 未找到原创弹窗';
})()
```

```js
// 3. 勾选协议（等 1 秒后执行）
(() => {
  function isVisible(el) {
    const s = window.getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  const labels = document.querySelectorAll('label');
  for (const l of labels) {
    if (l.innerText && l.innerText.includes('我已阅读并同意') && isVisible(l)) {
      const input = l.querySelector('input[type=checkbox]');
      if (input && !input.checked) { input.click(); return '已勾选协议'; }
      if (input && input.checked) { return '协议已勾选，无需操作'; }
    }
  }
  return 'ERROR: 未找到协议勾选项';
})()
```

```js
// 4. 在原创弹窗内点「确定」（等 1 秒后执行）
(() => {
  function isVisible(el) {
    const s = window.getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  const dialogs = document.querySelectorAll('.weui-desktop-dialog');
  for (const d of dialogs) {
    if (isVisible(d) && d.innerText.includes('文字原创') && d.innerText.includes('确定')) {
      const btn = [...d.querySelectorAll('button,a')].find(b => b.innerText.trim() === '确定');
      if (btn) { btn.click(); return '点击了确定'; }
      return 'ERROR: 找到弹窗但未找到确定按钮';
    }
  }
  return 'ERROR: 未找到原创弹窗';
})()
```

```js
// 5. 验证设置是否生效（等 3 秒后执行，会有原创校验过程）
(() => {
  const text = document.body.innerText;
  const match = text.match(/原创
(文字原创[^
]*)/);
  return match ? '✅ ' + match[1] : '未找到原创状态，当前：' + text.slice(text.indexOf('原创'), text.indexOf('原创') + 60);
})()
// 预期返回：✅ 文字原创 · 作者: 小龙虾有话说 · 已开启快捷转载
```

**注意事项：**
- 点「确定」后微信会进行原创校验，需等待约 10 秒，期间显示「原创校验中」
- 原创声明成功后右侧面板显示：「文字原创 · 作者: 小龙虾有话说 · 已开启快捷转载」
- 如已声明原创（面板显示上述内容），可跳过此步
- **不要**在原创弹窗内修改声明类型或作者，保持默认即可

### 4.7) 发表前硬闸（必须执行）

在点击最终「发表」前，必须先跑一次最小硬闸。没过就不允许继续点发布按钮。

```bash
python3 ${HERMES_SKILL_DIR}/scripts/prepublish_gate.py \
  --article-title "<当前文章标题>" \
  --creative-source ai_generated \
  --original-state text_original \
  --group-notify on \
  --scheduled off
```

说明：
- 如果原创声明弹了超时兜底并且你决定继续发，则把 `--original-state` 改成 `original_timeout_continue`
- 当前默认开启群发通知；除非老板明确要求关闭，才把 `--group-notify` 改成 `off`
- 这个脚本不会替你读 DOM；它的作用是把发布前最关键的几项变成**必须显式确认一次**的硬闸，避免漏设后直接发表

### 5) 走发表主流程

### 5.0) 尾段状态机（当前生效最小版）

正式发布尾段不要再靠「看起来像到了哪一步」临场乱点。当前最小生效状态机只认下面这些状态：

- `edit_ready`
- `prepublish_config_ready`
- `publish_entry_dialog`
- `publish_confirm_dialog`
- `submitted_pending_result`
- `waiting_safe_check_scan`
- `waiting_login_scan`
- `waiting_boss_confirm`
- `reader_side_in_review`
- `reader_side_published`
- `failed`

**AUTHORITATIVE_SIGNAL 优先级写死：**
1. 成功态只认后台「近期发表」里目标文章状态 = `审核中` / `已发表`
2. 中间态只认可见弹窗文案，不靠隐藏 DOM 猜
3. 阻塞态只认可见二维码 / 登录页 / 明确确认弹窗证据

**三类人工阻塞恢复点写死：**
- `safe_check -> submitted_pending_result`
- `login_scan -> edit_ready`
- `boss_confirm -> publish_confirm_dialog`

**为什么必须有 `submitted_pending_result`：**
最后确认刚点完、或者老板刚扫完码时，页面往往处于结果尚未显现的过渡期。这一段不能直接报成功，也不能继续盲点；必须先进入 `submitted_pending_result`，然后只用权威结果面（首页近期发表 / 新阻塞弹窗）重判下一步。

**当前控制面 helper（必须优先用，不要手写临时字段）：**
- 普通尾段状态迁移：
  `python3 /root/.hermes/shared-skills/forge/skills/wechat-article-forge/scripts/update_publish_tail_state.py --state-path <draft-dir>/pipeline-state.json --state-node <...> --signal-kind <...> --signal-summary "..." [--run-lock-path ...]`
- 人工阻塞落盘：
  `python3 /root/.hermes/shared-skills/forge/skills/wechat-article-forge/scripts/mark_publish_blocked.py ...`
- 进入 `reader_side_in_review` / `reader_side_published` / 失败后清理旧 blocker：
  `python3 /root/.hermes/shared-skills/forge/skills/wechat-article-forge/scripts/clear_publish_blocked_state.py ...`

**全局禁止动作：**
- 未重判状态前，连续盲点两个按钮
- 把“点击成功”当“业务成功”
- 把扫码成功当“已发表”
- 人工阻塞恢复后，不回恢复点直接乱点旧按钮


常见流程是三段:

1. 编辑页主按钮:**发表**
2. 发表弹窗:**发表**
3. 二次确认弹窗:**继续发表**(有时后续还会接微信验证)

推荐做法:每点一步后都重新 snapshot,不要盲点。

典型命令模式(每步后截图确认):

```bash
${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> screenshot /tmp/wechat-step.png
${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> click <ref>
${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> screenshot /tmp/wechat-step2.png
```

如果直接用 DOM 更稳,也可以用 `eval` 点:

```bash
${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> eval "document.querySelector('button.mass_send')?.click()"
```

### 5.1) 发表弹窗决策树（按可见弹窗文案，不靠猜）

这一步的原则是：**按当前可见弹窗类型走固定分支，弹窗一换，控制面状态也必须跟着换。**

#### 分支 A：`群发通知` / 群发通知开关

默认规则：
- 默认开启群发通知，走订阅用户群发路径
- 如果弹窗显示 `群发通知` 且有通知次数，确认群发通知处于开启状态后，点本层主按钮 `发表`
- 如果弹窗显示 `未开启群发通知`、`内容将展示在公众号主页` 或 `公众号主页`，说明当前没有走订阅用户群发路径；除非老板明确要求关闭群发通知，否则不要继续发表，先停下来报告
- 若随后出现二次确认弹窗，继续按可见文案确认目标路径，不要把“未开启群发通知 / 公众号主页”当作默认可接受状态

#### 分支 B：`原创校验超时`

如果出现：
- `原创校验超时`
- `暂时无法声明原创`
- `原创校验一旦完成，将对已群发并成功声明原创的文章补上原创标志`

这不是“群发通知开关”分支，而是**原创声明的超时分支**。

处理规则：
- 先确认当前目标仍是把这篇文章发出去，而不是等待原创校验完成
- 若要继续当前发布，点 `继续群发`（文案虽然叫这个，但这里处理的是“无原创标志先发出”的兜底确认，不等于替用户开启群发通知）
- 点完后立即重新 snapshot / eval，继续看下一层真实阻塞是什么

#### 分支 C：`正在增加群发次数` / `系统繁忙` / 临时冷却

如果出现：
- `正在增加群发次数，请于5分钟左右后再尝试群发`
- `系统繁忙，请稍后尝试`
- 其他明显的临时平台冷却 / 限流 / 稍后再试文案

处理规则：
- 不要继续盲点
- 不要维持旧的 `waiting_for=boss_scan` 之类人工阻塞态
- 立刻把 durable state 改写成**平台侧重试等待**：
  - `phase=publishing`
  - `status=waiting_retry`
  - `waiting_for=system_retry`
  - `required_user_action=null`
  - `relay_status=internal_retry`
- 写明 `retry_not_before` / 冷却窗口，再到点重试

#### 分支 D：`链接不合法`

如果出现：
- `链接不合法`
- `请勿添加其他公众号的主页链接`
- `此链接为预览链接，将在短期内失效`

处理规则：
- 立即停止发布点击链
- 先排查正文中的超链接、原文链接、来源字段、创作来源相关字段
- 在没定位出问题链接前，不要继续点 `确定` 之后再重复发表
- durable state 推荐直接落成确定性修复态，而不是继续挂在旧 publish / old blocker 上：
  - `phase=blocked`
  - `status=blocked`
  - `waiting_for=content_fix`（或等价显式修复目标）
  - `required_user_action=null`（若本轮由主 agent 自己修）或 `content_fix`（若必须转人工）
  - `relay_status=completed`（若已明确对外说明）或 `internal_retry`（若准备自行修后再试）

#### 分支 E：`微信验证` / `safe_check`

如果出现二维码验证：
- 先抓最新二维码
- 先自验图中确有二维码
- 再按第 6 节发给用户/上游
- durable state 必须切到最新 `safe_check` 阻塞态，覆盖旧 blocker

### ⚠️ DOM 安全规则（必须遵守，防止误触「退出登录」）

微信公众平台后台将 **10+ 个弹窗全部预渲染进 DOM**，其中包含「退出登录」等高危按钮（藏在「未授权切换账号」隐藏弹窗里），平时靠 CSS 控制显隐。曾于 2026-04-03 实际触发：子流程未加可见性过滤，误触隐藏弹窗里的「退出登录」，导致微信会话掉出，老板须二次扫码。

**强制规则：**

1. **可见性检测用 `getBoundingClientRect` + `getComputedStyle`，不要单独用 `offsetParent !== null`**
   WeUI modal 弹窗通常是 `position:fixed`，此时 `offsetParent` 恒为 `null`，用它过滤会把可见目标弹窗也误判为不可见。
2. **精确匹配目标弹窗**：用弹窗内容关键词（如「群发通知」「继续发表」）确认进入正确弹窗，再在弹窗内查找按钮。
3. **找不到按钮时必须明确报错**：返回包含 `ERROR:` 前缀的字符串，不允许静默跳过。
4. **每次点击后立即校验 URL**：若跳转到登录页（`/login`）或脱离 `mp.weixin.qq.com/cgi-bin/` 路径，停止操作并上报。

**安全点击模板（JS，通过 `${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> eval` 执行）：**

```js
(() => {
  function isDialogVisible(el) {
    const s = window.getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;  // 兼容 position:fixed
  }

  const TARGET_DIALOG_KEYWORD = '群发通知';  // 替换为目标弹窗关键词
  const TARGET_BUTTON_TEXT    = '发表';      // 替换为目标按钮文字

  const dialogs = document.querySelectorAll('.weui-desktop-dialog');
  for (const d of dialogs) {
    if (isDialogVisible(d) && d.innerText.includes(TARGET_DIALOG_KEYWORD)) {
      const btn = [...d.querySelectorAll('button,a,span')]
        .find(b => b.innerText.trim() === TARGET_BUTTON_TEXT);
      if (btn) {
        btn.click();
        return '点击成功：' + TARGET_BUTTON_TEXT;
      }
      return 'ERROR: 找到目标弹窗但未找到按钮「' + TARGET_BUTTON_TEXT + '」，停止操作';
    }
  }
  return 'ERROR: 未找到可见目标弹窗「' + TARGET_DIALOG_KEYWORD + '」，停止操作';
})()
```

**点击后 URL 验证（每步点击后立即执行）：**

```js
(() => {
  const url = location.href;
  if (url.includes('/login') ||
      (!url.includes('mp.weixin.qq.com/cgi-bin/appmsg') &&
       !url.includes('mp.weixin.qq.com/cgi-bin/home'))) {
    return 'WARN: 意外跳转 URL=' + url + '，检查是否误触退出登录，停止操作';
  }
  return 'OK: ' + url;
})()
```

⚠️ **重要:从草稿列表页点"发表"不可靠**(会被账号切换弹窗挡住)。务必先进**编辑页**再走发表流程:

```bash
# 进编辑页(从草稿列表页点编辑图标,新 tab 打开后 switch 2 切换,或直接拼 appmsgid URL)
${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> open "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77&appmsgid=<APPMSGID>&token=<TOKEN>&lang=zh_CN"
```

### 6) 处理"微信验证 / 安全验证"

正式发表时,经常会弹出 **微信验证**,要求管理员或运营者扫码确认。

识别信号:

- 弹窗标题:`微信验证`
- 文案含:`扫码后,请联系管理员进行验证`
- 页面里出现:`.safe_check.js_wxcheck0`
- 二维码元素常见为:`img.js_qrcode` 或 `.safe_check img.js_qrcode`

处理方式:

1. 从弹窗里抓 **当前最新** 的二维码 src。
2. 先判断它是不是最新的、是不是已经过了几分钟；如果用户刚说“没收到”,不要盲目复用旧码,必要时重新触发一次最新二维码。
3. **发送前先自验图片内容。** 无论是远程二维码 URL 还是本地截图，先自己确认图里真的有二维码；登录页、空白页、错误页、错误裁切图，一律禁止发送给用户。
4. **如果你是主 agent 直连用户**: 立刻把二维码图片直接发到当前对话。
5. **如果你是 `wechat-article-forge` 的 child / orchestrator 子流程**: 不要直接 `message` 用户。先把二维码保存到稳定路径（非 `/tmp`、按 `run_id` 唯一化）,然后返回 `need_user_action + safe_check_qr_path + waiting_for + required_user_action` 给上游。
6. 告诉上游/用户“尽快扫,过期很快”。
7. 用户回复"扫了"后,再继续检查页面状态。

抓二维码的常见方式:

```bash
${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> eval "(() => {
  const el = document.querySelector('.safe_check.js_wxcheck0 img.js_qrcode, .safe_check img.js_qrcode, img.qrcode.js_qrcode, img.js_qrcode');
  return el ? el.getAttribute('src') : 'NONE';
})()"
```

如果拿到的是相对路径(如 `/safe/safeqrcode?...`),记得补全成:

```text
https://mp.weixin.qq.com/safe/safeqrcode?...
```

### 6.1) `safe_check` 二维码的稳定落盘与 Feishu 发送顺序（按优先级）

**强制自检规则：** 发图前先本地打开或查看截图，确认画面中心确实是二维码，而不是登录页、空白页、错误弹窗、或裁切错位后的局部图。只要自己没看过，就不允许外发。

先说 child 流程的落盘规则：

- **先落稳定路径,再考虑发图。** 不要只把二维码 URL/截图塞在临时变量里等上游猜。
- 稳定路径必须是绝对路径、非 `/tmp`、按 run 唯一化；推荐 `<article-workspace>/media/wechat-safe-check/<sanitized-run-id>/safe-check.png`。
- 不要使用共享固定文件名或跨 run 复用同一路径。
- 只要是 `safe_check_scan` / `login_scan` 这类二维码接力，调用 durable 控制面脚本时必须显式带上 `--qr-verified`；没验过图，不允许把这张图写成当前权威二维码状态。
- 如果是 child 流程,返回结构化字段而不是直接 `message` 用户：

```json
{
  "status": "need_user_action",
  "waiting_for": "boss_scan",
  "required_user_action": "safe_check_scan",
  "safe_check_qr_path": "<article-workspace>/media/wechat-safe-check/<sanitized-run-id>/safe-check.png",
  "relay_status": "pending_parent_forward",
  "relay_dedupe_key": "<run-id>:safe_check_scan:1",
  "boss_notified_at": null,
  "qr_updated_at": "<now-iso>",
  "blocking_since": "<now-iso>",
  "timeout_at": "<now-plus-10m-iso>",
  "resume_context": {
    "browser_session": "default",
    "current_url": "<editor-page-url>",
    "appmsgid": "<appmsgid>"
  }
}
```

主 agent 直连用户时,再按下面顺序发到 Feishu:

按下面顺序来,别混着试:

1. **首选: `media=<绝对二维码 URL>`**
   - 微信 `safe_check` 弹窗里的二维码通常可直接补成 `https://mp.weixin.qq.com/safe/safeqrcode?...`
   - 这条链路会让 Hermes 先拉取图片,再走 Feishu 的 `image_key` 上传/发送流程,比“发本地路径字符串”靠谱得多。
2. **次选: `buffer + mimeType=image/png`**
   - 当页面里只有 canvas / blob / 已截图文件时使用。
   - 如果用 base64,要明确带 `mimeType`(或 `contentType`) 和最好带上 `filename`。
3. **本地文件只作为媒体源,也必须走 `media`**
   - 例如 `media: "/tmp/wechat-qr.png"`
   - 不要改成 `filePath: "/tmp/wechat-qr.png"` 期待它自动识别成图片消息。

### 6.2) 如果 `message` 返回 `ok:true`,但用户说“没收到二维码”

把这当成**可见性未确认**,不是“用户没认真看”。处理顺序:

1. 先回微信页面确认 `safe_check` 还在,二维码是否仍存在。
2. 如果二维码可能已旧了,**重新触发最新二维码** 再发,不要连续转发旧码。
3. 核对你这次发图是不是用了 `media`,而不是 `filePath` / 纯本地路径文本。
4. 优先改用 **绝对二维码 URL** 再发一次。
5. 发完后只问一句“现在能看到图吗/扫完回我”,不要在同一回合再叠加一条普通文本消息造成回显干扰。
6. 只有在用户明确说“看到了”或“已扫”后,才进入下一步状态检查。

### 7) 用户扫码后,不要口头假设成功

用户说"扫了"之后:

1. 等 1-2 秒
2. 检查是否还停留在 `.safe_check` 弹窗
3. 检查是否跳回首页
4. 检查"近期发表"里有没有该文章,状态是否为 **审核中** / **已发表**

推荐检查:

```bash
${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> eval "(() => JSON.stringify({
  url: location.href,
  hasSafe: !!document.querySelector('.safe_check.js_wxcheck0,.js_wxcheck0'),
  body: document.body.innerText.slice(-1500)
}))()"
```

### 8) 最终汇报方式

只汇报结果,不要把一长串中间细节倒给用户。

好汇报:
- "好了,已经提上去了。当前状态:审核中。"
- "这次卡在微信验证,我已经把新二维码发你了,扫完我继续。"
- "这次不是扫码问题,是运营规则学习答题拦住了,必须手机端完成。"

避免:
- 不确认状态就说"应该成功了"
- 把整页 HTML / 大段日志直接甩给用户

## 例外分支

### A. 出现"运营规则学习答题 / 历史违规记录"

如果页面或接口提示:

- 运营规则学习
- 学习答题
- 历史违规记录
- 类似 `720006`

结论要直接说清:

- **这是微信平台侧强制要求**
- **必须用户在手机端完成**
- **PC 后台不能合理绕过**

这时不要继续瞎点,不要假装还能自动完成。

### B. "继续群发"按钮点不动

如果你能看到"继续群发 / 继续发表"但点击无反应:

- 先重新 snapshot,确认是不是弹窗层叠
- 再检查是否有"运营规则学习提醒"或别的遮挡层
- 再判断是否其实是后端拦截,而不是前端点击问题

### C. browser-use 注意事项

- 优先接管现成 Chromium CDP 会话(`browser-use sessions` 查看活跃 session)
- 不要默认新开浏览器(`browser-use open ...` 容易超时)
- 当前默认 session 名是 `default`

### D. 不要把发送成功和用户看见混为一谈

在当前 Feishu 环境里,`message` 工具返回 `ok: true` 只能说明**出站调用成功**,不等于用户已经在客户端看见二维码图片。

所以 QR 场景的闭环应该是:

1. 你成功发出了媒体消息
2. 用户明确回复“看到了”或“已扫”
3. 你再去检查微信后台是否进入 **审核中 / 已发表**

少了第 2 步,都不算真正闭环。

## 输出模板

### 成功

```text
好了,已经提上去了。
当前状态:审核中。
```

### 需要重新登录

```text
会话过期了,我已经发你新的登录码。扫完回我一句,我立刻继续。
```

### 需要微信验证

```text
现在卡在微信验证,我已经把最新二维码直接发你了。尽快扫一下,扫完回我一句,我继续。
```

### 被学习答题拦住

```text
这次不是操作问题,是微信后台要求先完成运营规则学习答题。这个必须你在手机端做,PC 这边不能代过。做完告诉我,我再继续发。
```

## 已知环境经验（来自真实跑通 2026-03-30 / 2026-04-01）

- 真实可用路径：`${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id>` → 进入编辑页（`appmsgid` URL）→ 发表弹窗 → 继续发表 → 微信 safe_check 扫码 → 回首页看到"近期发表 = 已发表"。
- **从草稿列表页直接点"发表"不可靠**：会被"未授权切换账号"弹窗挡住，必须绕道走编辑页。
- 草稿 `appmsgid` 获取方式：点草稿列表的"编辑"按钮，会新 Tab 打开编辑页，用 `${HERMES_SKILL_DIR}/scripts/browser-use-agent.sh <agent-id> switch 2` 切换后从 URL 提取 appmsgid。
- 在这个环境里,文章正式提交成功后,后台首页的"近期发表"会显示:
  - 文章标题
  - 时间
  - **审核中** / **已发表**
- 这比只盯着编辑页弹窗更可靠。
- 2026-04-01 新补的关键经验：**Feishu 当前对话发二维码时,优先 `message.media=<绝对二维码 URL>`**；不要把本地路径塞进 `filePath` 指望它自动变成图片消息。
- 2026-04-01 新补的闭环纪律：**`message` 返回 `ok:true` 不等于用户看到了二维码**；必须等用户明确回复“看到了 / 已扫”,再去判断微信后台状态。
- 2026-04-03 新补的 DOM 安全经验：**微信后台存在 10+ 个预渲染隐藏弹窗，其中「未授权切换账号」弹窗含「退出登录」高危按钮。曾实际触发误触，导致会话掉出。** 所有 click 操作必须用 `getBoundingClientRect().height > 0` + `getComputedStyle` 检测可见性，不得单独使用 `offsetParent !== null`（WeUI fixed 定位弹窗的 `offsetParent` 恒为 `null`）。
- 2026-04-03 新补的设置弹窗经验：**微信编辑页的设置项弹窗（创作来源、原创声明等）弹出微信验证时，必须点右上角 X（`button.pop_closed`）关闭，不能点「取消」。** 点「取消」= 放弃操作不保存；点「X」= 关闭弹窗且设置已保存。
- 2026-04-03 封面图检测已移除：编辑页封面 DOM 选择器（`.cover_appmsg_thumb` 等）在当前环境下不可靠，会误报「无封面」，是已知误判根因。禁止在 Step 4 自动检测或上传封面。若发表时微信报「必须插入一张图片」，上报 `need_user_action` 由主 agent 处理。
- 2026-04-03 新补的原创声明流程：原创声明入口为 `.js_original_apply.js_edit_ori`；弹窗内默认状态为「文字原创 · 小龙虾有话说 · 快捷转载已开启」，无需修改，直接勾选协议→点确定；点确定后有约 10 秒原创校验期，正常现象；声明成功后右侧面板显示「文字原创 · 作者: 小龙虾有话说 · 已开启快捷转载」。

## 最后提醒

这是一条 **合规协作流程**,不是绕过风控流程。

你的职责是:
- 更快找到卡点
- 更稳复用会话
- 更及时把该扫的码发给用户
- 更准确确认最终状态

不是替用户绕过微信要求的真人验证或学习答题。
