/**
 * Centralised content for SEO landing pages so each route stays a short shell.
 * One file = one keyword cluster. Edit copy here without touching components.
 */

const RELATED_PAGES = [
  { label: 'AI TikTok Post Generator', href: '/ai-tiktok-post-generator' },
  { label: 'Viral Content Ideas Generator', href: '/viral-content-ideas-generator' },
  { label: 'Instagram Caption AI Generator', href: '/instagram-caption-ai-generator' },
  { label: 'Short-Form Video Ideas AI', href: '/short-form-video-ideas-ai' },
  { label: 'Content Automation Tool', href: '/content-automation-tool' },
  { label: 'Blog: What Makes Content Go Viral', href: '/blog/what-makes-content-go-viral-2026' },
];
const otherPages = (current) => RELATED_PAGES.filter((r) => r.href !== current);

export const TIKTOK = {
  seo: {
    title: 'AI TikTok Post Generator — Create Viral TikTok Content Instantly',
    description: 'Generate viral TikTok hooks, captions, and short-form video scripts with AI in seconds. CortexViral writes, schedules, and publishes TikTok posts that grow your following 24/7.',
    path: '/ai-tiktok-post-generator',
  },
  hero: {
    kicker: 'AI TikTok Post Generator',
    h1: 'Create Viral TikTok Posts with AI in Seconds',
    sub: 'CortexViral is a purpose-built AI TikTok post generator. Type your idea — get scroll-stopping hooks, full video scripts with timed scenes, captions, hashtags, and the optimal time to publish.',
    primaryCta: 'Generate a TikTok post free',
  },
  benefits: [
    { title: 'Hook-first AI', body: 'Every script opens with a 3-second hook tested against thousands of viral TikToks.' },
    { title: 'Scene-by-scene scripts', body: 'Get timed scenes with visual, voiceover and on-screen text — ready to film in one take.' },
    { title: 'Best-time scheduling', body: 'Built-in AI picks the next slot most likely to land on your audience\'s For You page.' },
  ],
  how: {
    h2: 'How to create a viral TikTok in 60 seconds',
    steps: [
      { n: '1', title: 'Drop in your idea or niche', body: 'Type one line: "summer skincare routine for oily skin". That is it.' },
      { n: '2', title: 'AI writes the full script', body: 'Hook + 3-5 scenes + caption + hashtags + music vibe — formatted for TikTok.' },
      { n: '3', title: 'Tweak and schedule', body: 'Edit anything, then schedule or publish at the AI-recommended peak time.' },
      { n: '4', title: 'Learn from performance', body: 'CortexViral tracks reach and engagement so the next post is even better.' },
    ],
  },
  useCases: [
    { title: 'Creators', body: 'Skip writer\'s block. Ship 5-10 short-form videos a week without burning out.' },
    { title: 'E-commerce brands', body: 'Turn product launches into viral UGC-style scripts your team can shoot in-house.' },
    { title: 'Agencies', body: 'Scale TikTok output across multiple client accounts with one workspace.' },
  ],
  faqs: [
    { q: 'Is the AI TikTok post generator free?', a: 'Yes — CortexViral has a free tier that lets you generate TikTok scripts and captions. Upgrade to Pro for unlimited generations, live publishing, and analytics.' },
    { q: 'Can it write hooks that actually go viral?', a: 'Our AI is trained on hook patterns that have produced billions of views across TikTok. Every script opens with a proven 3-second pattern interrupt.' },
    { q: 'Does it publish to TikTok directly?', a: 'Pro plan supports direct publishing once you connect your TikTok account via the Channels page. Otherwise, copy/paste the script — it is formatted to fit TikTok\'s caption limits.' },
    { q: 'How is this different from a generic AI writer?', a: 'CortexViral is purpose-built for short-form video. It outputs scenes, timing, hashtags, and music vibes — not generic prose.' },
  ],
  related: otherPages('/ai-tiktok-post-generator'),
};

export const VIRAL_IDEAS = {
  seo: {
    title: 'Viral Content Ideas Generator — AI That Finds Your Next Viral Post',
    description: 'Stuck on what to post? CortexViral\'s viral content ideas generator uses AI to surface trending topics, hooks, and angles for your niche in seconds. Free to try.',
    path: '/viral-content-ideas-generator',
  },
  hero: {
    kicker: 'Viral Content Ideas Generator',
    h1: 'Never Run Out of Viral Content Ideas Again',
    sub: 'Tell CortexViral your niche and audience. Our AI scans trending topics, viral patterns, and competitor moves to surface a fresh content idea — with a hook ready to post.',
  },
  benefits: [
    { title: 'Trend-aware ideas', body: 'AI tracks rising topics 24-48 hours before they peak so you ride the wave, not chase it.' },
    { title: 'Niche-specific', body: 'Tell us your industry and audience — every idea is calibrated to your brand voice.' },
    { title: 'Multi-platform', body: 'Each idea ships with TikTok, Instagram, X, and LinkedIn variants — one click, all platforms.' },
  ],
  how: {
    h2: 'From blank page to viral idea in 30 seconds',
    steps: [
      { n: '1', title: 'Describe your niche', body: 'Fitness, SaaS founder, lifestyle creator — anything works.' },
      { n: '2', title: 'AI proposes 5-10 ideas', body: 'Each idea includes a hook, the platform it\'s best suited for, and why it will land now.' },
      { n: '3', title: 'Pick one and generate', body: 'Click an idea — CortexViral expands it into a full post with captions and hashtags.' },
    ],
  },
  useCases: [
    { title: 'Solo creators', body: 'Replace 2 hours of brainstorming with 30 seconds of AI ideation.' },
    { title: 'Marketing teams', body: 'Fill an entire month\'s content calendar in one afternoon.' },
    { title: 'New accounts', body: 'Find your voice fast — AI suggests the angles working in your niche today.' },
  ],
  faqs: [
    { q: 'How does the viral content ideas generator work?', a: 'CortexViral combines real-time trend signals, viral pattern recognition, and your niche/audience inputs to surface the topics most likely to perform right now.' },
    { q: 'Can I use the ideas for any platform?', a: 'Yes. Every idea ships with platform-specific variants (TikTok, Reels, X, LinkedIn). One click expands an idea into a full publish-ready post.' },
    { q: 'Are the ideas original?', a: 'AI suggests angles, hooks, and topics — final copy is generated fresh for your brand. We never recycle other creators\' captions.' },
  ],
  related: otherPages('/viral-content-ideas-generator'),
};

export const INSTAGRAM = {
  seo: {
    title: 'Instagram Caption AI Generator — Free Captions in Your Voice',
    description: 'Generate scroll-stopping Instagram captions with AI. CortexViral writes captions, hashtags, and CTAs in your brand voice — free to start.',
    path: '/instagram-caption-ai-generator',
  },
  hero: {
    kicker: 'Instagram Caption AI Generator',
    h1: 'AI Instagram Captions That Stop the Scroll',
    sub: 'CortexViral writes hook-first Instagram captions, optimised hashtags, and CTAs in your voice — from a single line of input. Free, fast, and ready to publish.',
  },
  benefits: [
    { title: 'Voice-matching AI', body: 'Trained on your existing posts to keep captions on-brand and unmistakably yours.' },
    { title: 'Caption + hashtags + CTA', body: 'Every output ships with 15-25 high-relevance hashtags and a tested CTA.' },
    { title: 'Built for Reels and feed', body: 'Toggle between Reel scripts and static-feed captions — formatted to fit each.' },
  ],
  how: {
    h2: 'Three steps to a perfect Instagram caption',
    steps: [
      { n: '1', title: 'Describe the post', body: 'A photo, a product, a thought — one line is enough.' },
      { n: '2', title: 'Pick a tone', body: 'Friendly, professional, playful, inspirational, urgent.' },
      { n: '3', title: 'Generate and refine', body: 'Get caption + hashtags + CTA. Regenerate variants until it feels right.' },
    ],
  },
  faqs: [
    { q: 'How many Instagram captions can I generate?', a: 'Unlimited captions on the Pro plan. Free tier includes generous monthly credits.' },
    { q: 'Will hashtags actually help my reach?', a: 'CortexViral picks hashtags by niche relevance and recent performance — not blind volume — so they actually drive discovery.' },
    { q: 'Can it write for Reels too?', a: 'Yes. Toggle to "Reel script" and the AI outputs hook + scenes + on-screen text + caption.' },
  ],
  related: otherPages('/instagram-caption-ai-generator'),
};

export const SHORT_FORM = {
  seo: {
    title: 'Short-Form Video Ideas AI — Reels, Shorts & TikTok Scripts',
    description: 'AI-powered short-form video ideas generator for TikTok, Instagram Reels, and YouTube Shorts. Get hook-first scripts with scenes, captions, and trending hashtags.',
    path: '/short-form-video-ideas-ai',
  },
  hero: {
    kicker: 'Short-Form Video AI',
    h1: 'AI Short-Form Video Ideas for Reels, Shorts & TikTok',
    sub: 'CortexViral generates hook-first short-form video scripts — Reels, Shorts, TikToks — with scenes, voiceover lines, on-screen text, and trending music suggestions.',
  },
  benefits: [
    { title: 'Triple-platform ready', body: 'One script outputs as TikTok, Reels, and YouTube Shorts — formatted for each.' },
    { title: 'Hook engineering', body: 'AI tests dozens of hook patterns and selects the one most likely to land in your niche.' },
    { title: 'Scene + sound', body: 'Get timed scenes with visual cues and music-vibe suggestions you can drop into CapCut.' },
  ],
  how: {
    h2: 'Idea to published Reel in under 3 minutes',
    steps: [
      { n: '1', title: 'Pick a niche or topic', body: 'Or let AI suggest one based on what is trending in your space.' },
      { n: '2', title: 'AI writes the script', body: 'Full structure: hook (0-3s), reveal (4-15s), CTA (15-30s).' },
      { n: '3', title: 'Film and schedule', body: 'Shoot, paste captions, schedule for the AI-recommended peak slot.' },
    ],
  },
  faqs: [
    { q: 'Can one script work on TikTok, Reels, and Shorts?', a: 'Yes — CortexViral generates a base script and platform-tailored captions, so one filming session yields three publishes.' },
    { q: 'Does it suggest trending audio?', a: 'AI flags music vibes (upbeat, melancholic, hype) — you can pair them with any trending sound on each platform.' },
  ],
  related: otherPages('/short-form-video-ideas-ai'),
};

export const AUTOMATION = {
  seo: {
    title: 'Content Automation Tool — AI That Posts For You 24/7',
    description: 'CortexViral is the all-in-one content automation tool: AI writes, schedules, and publishes across 38+ social channels — so your brand grows while you sleep.',
    path: '/content-automation-tool',
  },
  hero: {
    kicker: 'Content Automation Tool',
    h1: 'The AI Content Automation Tool That Runs 24/7',
    sub: 'CortexViral automates the entire social media loop: ideation, generation, scheduling, publishing, and performance learning — across TikTok, Instagram, X, LinkedIn, and 30+ more.',
  },
  benefits: [
    { title: 'Schedule + auto-publish', body: 'Background scheduler flips drafts to live posts at the exact peak window for each channel.' },
    { title: 'Multi-platform from one source', body: 'Write once. AI tailors the post for every connected social account automatically.' },
    { title: 'Learns from performance', body: 'Each post feeds analytics back into the AI to improve hooks, timing, and tone over time.' },
  ],
  how: {
    h2: 'How content automation actually works',
    steps: [
      { n: '1', title: 'Connect your channels', body: 'TikTok, Instagram, X, LinkedIn, YouTube — connect in one click each.' },
      { n: '2', title: 'AI fills your calendar', body: 'Set a cadence (e.g. 3 posts/day per channel) and AI populates a full week.' },
      { n: '3', title: 'Approve or auto-publish', body: 'Pick: review every post, or let the scheduler push them live automatically.' },
      { n: '4', title: 'Read the weekly report', body: 'Every Monday, CortexViral emails what worked, what didn\'t, and what to try next.' },
    ],
  },
  faqs: [
    { q: 'How many channels can I automate?', a: 'CortexViral supports 38+ channels including TikTok, Instagram, X, LinkedIn, YouTube, Facebook, Pinterest, Threads, Reddit, Substack, Medium, and more.' },
    { q: 'Will posts look auto-generated?', a: 'No. AI is trained on your existing voice, tone, and brand style. Outputs are indistinguishable from posts written by your team.' },
    { q: 'Can I still write some posts manually?', a: 'Absolutely. The calendar is fully editable — use AI for 80%, write the rest yourself.' },
  ],
  related: otherPages('/content-automation-tool'),
};
