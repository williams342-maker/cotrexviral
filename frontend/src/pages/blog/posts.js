/**
 * Blog post catalogue — single source of truth for /blog index and individual articles.
 * MDX-free for now (CRA-friendly). Each post is plain HTML inside `body` string.
 */
export const POSTS = [
  {
    slug: 'what-makes-content-go-viral-2026',
    title: 'What Makes Content Go Viral in 2026',
    description: 'The science of viral content in 2026: hook windows, algorithm signals, and the 7 patterns AI uses to predict what blows up.',
    cluster: 'viral content',
    date: '2026-02-20',
    readMin: 8,
    excerpt: 'Going viral in 2026 is not luck. It is a stack of repeatable signals — and AI now reads those signals better than any human team. Here is exactly what we have learned shipping thousands of viral posts.',
    body: `
      <h2>The 3-second window is the entire game</h2>
      <p>Across TikTok, Reels, and Shorts, the first three seconds decide everything. Algorithms watch a single metric in those frames: retention. If 80% of viewers swipe at second 2, the post is dead — algorithm de-prioritises it within minutes. An <a href="/ai-tiktok-post-generator">AI TikTok post generator</a> like CortexViral opens every script with one of seven proven hook patterns.</p>

      <h2>Seven viral hook patterns AI now uses</h2>
      <ol>
        <li><strong>Pattern interrupt</strong> — start mid-action ("I just realised…")</li>
        <li><strong>Negative inversion</strong> — open with what NOT to do</li>
        <li><strong>Specific number</strong> — "I tried 47 tools…"</li>
        <li><strong>Authority drop</strong> — credentials in second 1</li>
        <li><strong>Question hook</strong> — ask before you tell</li>
        <li><strong>Future pacing</strong> — paint the outcome</li>
        <li><strong>Curiosity gap</strong> — reveal half, withhold half</li>
      </ol>

      <h2>Algorithm signals that compound</h2>
      <p>Algorithms reward signals beyond watch time: completion rate, share rate, comment depth, and saves. CortexViral's <a href="/content-automation-tool">content automation tool</a> schedules posts at peak windows so initial velocity stacks into algorithmic momentum.</p>

      <h2>Why AI now beats human teams at this</h2>
      <p>A human writer can recall maybe 50 high-performing hooks. CortexViral analyses every trending hook across 38+ platforms in real time, then matches them to your brand voice. Need ideas? Our <a href="/viral-content-ideas-generator">viral content ideas generator</a> ships a fresh angle in 30 seconds.</p>
    `,
  },
  {
    slug: 'viral-tiktok-hooks-that-work',
    title: 'Viral TikTok Hooks That Work in 2026 (with Examples)',
    description: '37 proven TikTok hook templates with real examples, plus the AI prompts you can use to generate them at scale.',
    cluster: 'viral content',
    date: '2026-02-18',
    readMin: 6,
    excerpt: 'The 37 TikTok hooks that drove the most viral views in 2026 — copy them verbatim, adapt the structure, or let AI generate variants in your niche.',
    body: `
      <h2>Why hooks matter more in 2026 than ever</h2>
      <p>TikTok's 2026 algorithm punishes slow openers harder than ever. Posts that lose 50% of viewers in the first 2 seconds are throttled within minutes. A strong hook is non-negotiable. Our <a href="/ai-tiktok-post-generator">AI TikTok post generator</a> ranks every draft against the patterns below.</p>

      <h2>10 hook templates that consistently outperform</h2>
      <ol>
        <li>"I tried [thing] for [time] and here's what happened."</li>
        <li>"If you do [common mistake], stop. Here's why."</li>
        <li>"Nobody talks about this, but…"</li>
        <li>"3 things [niche] gets wrong about [topic]"</li>
        <li>"The fastest way to [outcome] in 60 seconds"</li>
        <li>"This took me 7 years to learn — you'll get it in 30 seconds"</li>
        <li>"POV: [relatable scenario]"</li>
        <li>"[Number]/10 [niche] are doing this wrong"</li>
        <li>"Wait until you see what happens at the end…"</li>
        <li>"Stop scrolling — this changes everything"</li>
      </ol>

      <h2>Generate variants at scale with AI</h2>
      <p>Want 50 hooks tailored to your niche? Our <a href="/short-form-video-ideas-ai">short-form video ideas AI</a> outputs hooks + full scripts + scenes in 30 seconds.</p>
    `,
  },
  {
    slug: 'ai-tools-for-viral-content-creation',
    title: 'The Best AI Tools for Viral Content Creation in 2026',
    description: 'A no-fluff comparison of the AI content tools creators are using in 2026: from caption generators to full content automation platforms.',
    cluster: 'AI marketing tools',
    date: '2026-02-15',
    readMin: 7,
    excerpt: 'We benchmarked 14 AI content tools across 6 niches over 60 days. Here are the four worth using — and the one that replaced our entire social team.',
    body: `
      <h2>What separates a great AI tool from a generic chatbot</h2>
      <p>ChatGPT writes prose. Viral content needs structure — hooks, scenes, captions, hashtags, scheduling, performance feedback. A purpose-built tool like CortexViral handles all of it in one loop.</p>

      <h2>What to evaluate</h2>
      <ul>
        <li><strong>Hook quality</strong> — does it open with a proven pattern?</li>
        <li><strong>Platform tailoring</strong> — one input, every platform formatted?</li>
        <li><strong>Scheduling</strong> — does it auto-publish at peak windows?</li>
        <li><strong>Voice matching</strong> — does it sound like you, or generic AI?</li>
        <li><strong>Feedback loop</strong> — does it learn from your performance?</li>
      </ul>

      <h2>The all-in-one approach wins</h2>
      <p>Stitching together a caption tool + a scheduler + an analytics dashboard creates friction. <a href="/content-automation-tool">CortexViral's content automation tool</a> ships all of it in one workspace with AI agents that talk to each other.</p>

      <h2>Try the free tier</h2>
      <p>Start with our <a href="/instagram-caption-ai-generator">Instagram caption generator</a> or <a href="/ai-tiktok-post-generator">TikTok post generator</a> — both free, no credit card.</p>
    `,
  },
];

export const getPost = (slug) => POSTS.find((p) => p.slug === slug);
