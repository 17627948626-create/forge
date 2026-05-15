# Engines and behavior

## Stable on this machine
- Sogou WeChat
- Sogou Web
- DuckDuckGo HTML
- Startpage
- Brave Search
- Hermes built-in web search/fetch
- Tavily search / extract (optional only if available)

## Degraded / avoid as primary
- Bing result pages
- Eastmoney result pages

## Mental model
- Hermes built-in web search is the default broad discovery layer
- direct search-result URLs are optional URL-template discovery surfaces
- source-page fetch/open is the evidence layer
- `tavily-search` is only an optional fallback/enhancement layer

## Practical recommendation
Use Hermes web search for breadth, add direct search-result URLs when useful, then confirm with source-page fetches.
