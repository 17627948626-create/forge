# LEGACY ONLY — Humanizer Removed From Active Pipeline

Humanizer is no longer part of the active `wechat-article-forge` pipeline.

Current rule:

```text
Reviewer pass = content final.
No post-review prose rewriting.
```

New runs must not spawn a Humanizer child, must not generate `final.md` as a Humanizer artifact, and must not use this prompt as a fallback tone-cleaning step.

真人化写作的责任已经前移：

- Writer 负责从第一稿开始写出可发布的人味、节奏和作者感。
- Reviewer 负责判断 Voice 是否达标；不达标就退回 Writer revise。
- Layout 只负责微信端 render adaptation，不负责润色正文。

This file is kept only so historical references do not break during migration.
