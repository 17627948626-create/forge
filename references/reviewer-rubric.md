# Reviewer Rubric - WeChat 公众号 Article Quality

> v7 - 2026-04-22. Unified-score gate + author-presence revision.
> Reviewers judge **the text on the page**, not platform outcomes.
> A reviewer cannot predict shares, open rate, or distribution luck. A reviewer can judge whether the draft is specific, original, emotionally alive, readable on mobile, and voiced like a real person with a real point of view.

## Review Protocol (current gate semantics)

Reviewer output uses **one unified scoring gate**.

Hard rule:
- **Final pass requires `weighted_total >= review_pass_threshold`**
- **`review_pass_threshold` lives in exactly one authority source: `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/config.json` → `review_pass_threshold`**
- Severe problems are **not** managed as a separate blocker gate; they must be reflected as heavy score damage inside the relevant dimensions, especially `Voice`, `Completion Power`, `Title`, and `Insight Density`
- `upgrade_suggestions` remain **non-blocking by default**
- `upgrade_suggestions` should default to **at most 3 items**
- Review should still call out severe issues clearly, but the release decision comes back to the total score

Reviewer also has a **保亮点义务**:
- point out the **one judgment / sharp line** most worth preserving
- point out the **screenshot-worthy paragraph or emotional scene** most worth preserving, if present

This duty is subordinate to gatekeeping: preserving a highlight is not a reason to pass a draft whose total score is still below the line.

## Diagnostic Dimensions

### Insight Density (洞察密度) - Weight: 14%

How many genuinely surprising, non-obvious ideas per 1000 characters? This is the article's core value proposition.

| Score | Criteria |
|-------|----------|
| 9-10 | Multiple 「我靠，没想到」 moments. Each major section delivers a non-obvious insight backed by evidence. The ideas are specific and nameable, not vague gestures at complexity. |
| 7-8 | 1 strong main insight plus at least 1 useful secondary insight; some sections still feel predictable or overlapping. |
| 5-6 | Competent summary, but too much overlap / restatement and no meaningful secondary insight. |
| 3-4 | Obvious points stated with confidence. Reader likely knew this already. |
| 0-2 | Zero insight. Pure filler or platitude. |

**Key test:** For each section, can you state the non-obvious claim in one sentence? If the sentence is something any competent generalist would say, score ≤6.

### Originality (新鲜感) - Weight: 14%

Originality is not novelty theater. It is whether the framing feels earned and distinctly this article's own.

| Score | Criteria |
|-------|----------|
| 9-10 | Genuinely new insight or framing. Reader thinks 「我之前没这样想过」. The core idea is specific, nameable, and not easily swappable with 1000 similar articles. |
| 7-8 | Fresh angle on a known topic. Not groundbreaking, but clearly not the most generic take. |
| 5-6 | Competent synthesis of existing ideas. Well-written but familiar. |
| 3-4 | Rehashed talking points. Could be produced from the same public source pack by almost anyone. |
| 0-2 | Zero original thought. |

### Emotional Resonance (情感共鸣) - Weight: 20%

The reader should feel seen, unsettled, fired up, relieved, or newly alert. Emotion must be earned by judgment, evidence, and scene.

| Score | Criteria |
|-------|----------|
| 9-10 | Hits the reader in the gut. Emotion is earned, not pushed. The article contains a visible emotional arc: setup → tension → release / revelation. |
| 7-8 | Real emotional moments but some flat stretches. |
| 5-6 | Occasional emotional flickers. Mostly intellectual, not visceral. |
| 3-4 | Flat. Reader feels little beyond information intake. |
| 0-2 | Actively annoying: preachy, manipulative, or hollowly sentimental. |

### Completion Power (完读力) - Weight: 18%

This predicts whether each screen earns the next scroll.

| Score | Criteria |
|-------|----------|
| 9-10 | Unputdownable. Every paragraph creates a micro-reason to continue: unresolved tension, concrete stakes, surprising turn, or accumulating pattern. Mobile rhythm is strong. |
| 7-8 | Strong pull with 1-2 flat spots. |
| 5-6 | Starts well, sags in the middle. Reader finishes more from duty than desire. |
| 3-4 | Only the opening is interesting. Most readers likely bail before halfway. |
| 0-2 | Even the opening fails. No hook, no pace, no reason to stay. |

**Mobile check:** Is there ever a full phone screen (5+ lines) without a visual break, subheading, bold text, or new paragraph? Each occurrence = -1 pressure on `Completion Power`.

**Argument closure check (论证闭环):** For 观点类 articles ≤2000 characters: does the article complete a full argument loop — claim → evidence → implication? If not, `Completion Power` should usually score ≤6 regardless of prose polish.

### Voice (语感) - Weight: 18%

Natural Chinese that sounds like **a specific person thinking on the page**, not a committee or a pattern engine.

This is the primary detector for **作者不在场感** and visible AI flavor.

Reviewer must explicitly judge these four sub-signals inside `Voice`:
1. **Opening interchangeability** — could the opening be pasted onto 30-50 other articles on the same topic without anyone noticing?
2. **Author presence** — do we feel a live judgment, a live implication, or a lived reading of the material?
3. **Transition dependence** — is the article advancing through cause / conflict / scene / implication, or mostly through template connectors?
4. **Ending sloganism** — does the ending land on a concrete implication / choice / cost, or dissolve into a banner-like summary line?

High-risk manufactured-language signals include but are not limited to:
- `随着……的发展`
- `总而言之 / 综上所述 / 总之`
- `值得注意的是 / 值得一提的是`
- `具体而言 / 具体来说`
- `换言之 / 也就是说`
- `我们不难发现`
- `由此可见`
- `毫无疑问 / 毋庸置疑`
- `全面赋能`
- `未来已来`
- `不仅如此 / 更重要的是`
- `底层逻辑 / 认知升级`
- polite report-style openings that delay the article's judgment
- interchangeable endings that could close any article in the category

Hard rule for this dimension:
- A single isolated template phrase does not automatically fail `Voice`
- But **high density, repeated dependence, or using such phrases as the article's main progression logic** should materially lower `Voice`
- If the author still does not feel present behind the text, `Voice` should usually score **≤6**
- If the draft still needs a downstream tone-cleaning pass to feel publishable, Reviewer must return `revise`; Reviewer pass freezes body text

`Voice` should fail or receive heavy score damage when:
1. The article sounds like generic platform prose
2. The opening delays judgment through polite setup or generic background
3. The article relies on template transitions instead of cause, conflict, scene, or evidence
4. The author is absent from the argument
5. Paragraph rhythm is too uniform
6. Abstract nouns replace concrete objects, actions, or costs
7. The ending turns into a generic summary, moral, or slogan

When `Voice` is a material issue, feedback must be executable:
- cite the exact passage
- explain why it sounds manufactured or absent
- tell Writer what concrete repair to make
Do **not** write vague advice like 「更自然一点」.

| Score | Criteria |
|-------|----------|
| 9-10 | Unmistakably human. Strong personality. Sentence rhythm varies naturally. Specific personhood is present on the page. Opening lands quickly. Ending lands concretely. Little to no visible template dependence. |
| 7-8 | Mostly natural with minor stiff patches. Some familiar templates may appear, but they do not control the article's rhythm or the sense of authorship. |
| 5-6 | Functional but generic. Noticeable template connectors / summary lines accumulate. Author-presence is intermittent or weak. |
| 3-4 | Stiff, formal, over-processed, or awkwardly mixed in register. Heavy visible template dependence makes the text feel manufactured. |
| 0-2 | Obvious 翻译腔 / 教材腔 / 鸡汤腔 / dense AI-template smell. The author is effectively absent behind the language. |

### Title (标题) - Weight: 16%

Title determines the click. A strong title promises a specific judgment the body actually earns.

**Search visibility rule (微信搜一搜 SEO):** Title should contain at least one high-intent keyword integrated naturally — prefer specific terms (`Agent`, `大模型`, `人形机器人`, `OpenAI`, `Claude`, `推理模型` …) over vague umbrellas (`AI`, `技术`). If title has no recognizable keyword, cap `Title` at 6.

**Argument visibility rule:** Title must signal a specific judgment, conflict, or counter-intuitive claim — not merely announce the topic.

**Lead consistency check (正文前300字):** Reviewer must verify that the keyword in the title also appears naturally in the opening 300 characters and that the core claim is established there. If not, deduct 1 point from `Title`.

| Score | Criteria |
|-------|----------|
| 9-10 | Irresistible curiosity gap. Reader wants to click now. ≤26 characters. Specific. Delivers what it promises. Contains one specific high-intent keyword naturally integrated. Lead echoes the keyword and lands the core claim. |
| 7-8 | Good click appeal. Slightly generic keyword choice or slightly bolted-on integration, but still strong. |
| 5-6 | Descriptive but not compelling. Or compelling but weak on search visibility. Or too swappable with many articles on the same topic. |
| 3-4 | Weak, too long, misleading, or keyword-stuffed. |
| 0-2 | Terrible or clickbait the article does not deliver. |

---

## Weight Summary

| Dimension | Weight | What Reviewer Observes |
|-----------|--------|----------------------|
| Insight Density (洞察密度) | 14% | Non-obvious ideas per section |
| Originality (新鲜感) | 14% | Unique framing vs rehashed takes |
| Emotional Resonance (情感共鸣) | 20% | Earned emotional arc in the text |
| Completion Power (完读力) | 18% | Pacing, hooks, micro-tension per scroll |
| Voice (语感) | 18% | Author presence, naturalness, rhythm, low template dependence |
| Title (标题) | 16% | Specificity, judgment, click value, search visibility |
| **Total** | **100%** | |

## Pass/Fail Criteria

- **Pass:** `weighted_total >= review_pass_threshold`
- **Fail / Revise:** `weighted_total < review_pass_threshold`

`weighted_total` is the **only release gate**.
Other per-dimension signals remain diagnostic unless the caller explicitly re-enables extra floors.

### Severe Issues (must be fused into scoring, not split as separate blockers)

These issues should trigger **material score damage** in the relevant dimensions and be surfaced under `critical_issues`:

1. **标题党 / 过度承诺** — title or opening promises a strength the body does not earn
2. **严重教材腔 / 翻译腔 / 鸡汤腔** — not just one stiff sentence, but a real drag on readability or trust
3. **严重灌水** — whole paragraphs add no new information, no new judgment, and no emotional movement
4. **严重模板化** — structure and language collapse into a replaceable template product
5. **核心判断不成立 / 明显失焦** — the main judgment does not stand, or the article drifts off the real question
6. **与 brief 明显冲突（含偷漂移）** — conflict with agreed direction, boundaries, or thesis
7. **关键论证支撑不足** — core judgment lacks enough factual support, or the evidence chain breaks
8. **推断越界 / 事实边界越界** — unsupported inference written as fact, or conclusion stronger than evidence boundary allows
9. **作者不在场** — the text is competent, but the author never truly shows up in the argument
10. **开头 / 结尾可替换性过高** — opening or ending reads like a generic category template rather than this article's own move

### UPGRADE_SUGGESTIONS (non-blocking by default)

Use this section for improvements that would make the piece sharper, more elegant, more spreadable, or more memorable **without affecting publishability**. Keep it short: default **max 3 items**.

Examples:
- a section can be compressed for stronger rhythm
- a sharper line exists but is buried
- one emotional beat can land harder
- a better paragraph order may improve momentum

## Anti-Patterns

- **翻译腔** — English-mirrored syntax
- **鸡汤化** — empty motivational lift with no earned content
- **教材体** — academic tone where a live voice should exist
- **标题党** — title promises what body does not deliver
- **流水账** — listing without a point
- **万金油文** — article so generic it could fit almost any topic with minor substitutions
- **套路结构** — the whole article runs on a predictable shell instead of real progression
- **作者不在场** — facts are present, but the mind behind them never truly enters the page

## Feedback Format

Always return review in this structure:

```json
{
  "decision": "pass" | "revise",
  "critical_issues": [
    {
      "type": "issue_type",
      "issue": "why this issue materially hurts the score",
      "quote": "relevant passage",
      "fix_direction": "narrow, concrete repair direction",
      "penalized_dimensions": ["voice", "completion_power"]
    }
  ],
  "upgrade_suggestions": [
    {
      "issue": "non-blocking improvement",
      "quote": "relevant passage",
      "suggestion": "specific upgrade direction"
    }
  ],
  "preserve": {
    "judgment_or_edge": "the one judgment / sharp line most worth preserving",
    "paragraph_or_scene": "the screenshot-worthy paragraph or emotional scene most worth preserving, if any"
  },
  "voice_observations": {
    "opening_interchangeability": "low | medium | high",
    "author_presence": "low | medium | high",
    "transition_template_dependence": "low | medium | high",
    "ending_sloganism": "low | medium | high",
    "notes": "required when Voice is a material issue"
  },
  "scores": {
    "weighted_total": 0,
    "notes": "required final gate: pass requires weighted_total >= review_pass_threshold (from config.json)"
  }
}
```

Do **not** omit the `scores` block in a final adjudication round, because `weighted_total` is the single pass/fail gate.

For Voice failures, prefer a concrete `critical_issues` item like:

```json
{
  "type": "voice_author_absence",
  "issue": "第二节连续几段都在解释材料，但作者判断不在场，读起来像平台通稿",
  "quote": "relevant passage",
  "fix_direction": "退回 Writer：先重写开头，尽快落一个明确判断；再把这一节改成“判断 + 具体代价/场景 + 证据”结构",
  "penalized_dimensions": ["voice", "completion_power"]
}
```

## Data Sources

- NewRank 2024 Annual Report: 30.78万篇 10W+ articles (7 per 10,000)
- 36kr/NewRank 2026 Study (7,242 accounts): 1.9% open rate, 4.3% headline, 50% completion of openers, 16.1% reads from shares
- 南方传媒书院 / 澎湃 10W+ Analysis: 10 traits of viral articles
- WeChat platform metrics: 完读率 avg 15-25%, emotional content 45-60%
- WeChat recommendation algorithm signals: 完读率, 分享, 点赞/在看, 收藏, 留言
