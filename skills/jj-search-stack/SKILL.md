---
name: jj-search-stack
version: 2.0.0
description: >-
  Use for Hermes web research, Chinese/global source discovery, WeChat article
  hunting, finance/tech/news monitoring, and forge topic research. Prefer this
  skill when result quality depends on trying more than one search entrypoint,
  verifying source pages, or keeping discovery snippets separate from evidence.
metadata:
  hermes:
    tags:
      - search
      - research
      - wechat
      - topic-discovery
---

# JJ Search Stack

This is a Hermes-adapted search policy. It is not a separate search backend.
Use Hermes' built-in web search/fetch tools first, and use direct search-result
URLs only when they improve discovery.

## When To Use

Use this skill for:

- WeChat / 公众号 article discovery
- forge researcher work
- Chinese news, tech, finance, and macro topic research
- multi-engine source discovery
- situations where snippets are not reliable enough

For one-off factual lookups, native Hermes web search alone is enough.

## Core Rule

Search pages are discovery. Source pages are evidence.

Do not cite or rely on a search-result snippet until you have opened and checked
the candidate source page itself.

## Entry Points

Preferred order:

1. Hermes built-in web search for the broad query.
2. Sogou WeChat for public-account article hunting:
   `https://weixin.sogou.com/weixin?type=2&query=QUERY&page=1`
3. Sogou Web for Chinese web discovery:
   `https://www.sogou.com/web?query=QUERY`
4. DuckDuckGo HTML / Startpage for lightweight global discovery.
5. Brave Search as an extra global signal when needed.

Always URL-encode `QUERY`.

Avoid using Bing result pages and Eastmoney result pages as primary discovery
surfaces on this machine; they have produced low-signal or shell-only pages.

## Workflow

1. Start with Hermes web search and collect candidate URLs.
2. If WeChat public articles matter, query Sogou WeChat directly.
3. Open candidate source pages, not just search pages.
4. Prefer named, attributable, closer-to-primary sources.
5. Return a compact shortlist:
   - title
   - URL
   - source type: search hit / verified source / official source
   - why relevant
   - verified: yes/no
   - confidence: high/medium/low

## Forge Researcher Use

For article topic research:

- keep `discovery_source` separate from `evidence_source`
- verify at least one source page for every factual claim used downstream
- for fast-moving topics, compare publish dates and event dates explicitly
- for WeChat article inspiration, use Sogou WeChat as discovery but verify the
  actual `mp.weixin.qq.com` page before using it

Tavily or other external search CLIs are optional only. Do not require them for
Hermes profiles.
