import React, { useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Rocket, Sparkles, ArrowLeft, Mail, MessageCircle, FileText,
  Loader2, CheckCircle2, AlertTriangle, ImageIcon, Calendar, Target,
  ChevronRight, Globe, Send, Upload,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { API } from '../../context/AuthContext';

/* Campaigns — Phase C surface.
 *
 * List view: every campaign the user has built, status + counts.
 * Detail view (?id=...): unified workspace with five tabs:
 *
 *   Overview  — campaign meta, build step trace, brief link
 *   Posts     — social variants per platform (copyable)
 *   Emails    — 3-touch email sequence
 *   Landing   — landing-page outline (headline → sections → CTA)
 *   Creatives — Phase B images attached to this campaign
 */

const STATUS_TONE = {
  building: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  complete: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  failed:   'bg-rose-500/15 text-rose-300 border-rose-500/30',
};

const PLATFORM_TONE = {
  facebook:        'text-sky-300 border-sky-500/30 bg-sky-500/10',
  instagram:       'text-fuchsia-300 border-fuchsia-500/30 bg-fuchsia-500/10',
  instagram_story: 'text-fuchsia-300 border-fuchsia-500/30 bg-fuchsia-500/10',
  pinterest:       'text-rose-300 border-rose-500/30 bg-rose-500/10',
  linkedin:        'text-cyan-300 border-cyan-500/30 bg-cyan-500/10',
  tiktok:          'text-zinc-200 border-white/20 bg-white/[0.06]',
  youtube:         'text-rose-300 border-rose-500/30 bg-rose-500/10',
  youtube_shorts:  'text-rose-300 border-rose-500/30 bg-rose-500/10',
  email:           'text-emerald-300 border-emerald-500/30 bg-emerald-500/10',
  blog:            'text-amber-300 border-amber-500/30 bg-amber-500/10',
  google_ads:      'text-emerald-300 border-emerald-500/30 bg-emerald-500/10',
  x:               'text-zinc-200 border-white/20 bg-white/[0.06]',
};


export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();
  const activeId = searchParams.get('id');
  const [active, setActive] = useState(null);

  const loadList = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/campaigns?limit=80`,
                                  { withCredentials: true });
      setCampaigns(r.data?.campaigns || []);
    } catch (_e) { setCampaigns([]); }
    finally { setLoading(false); }
  }, []);

  const loadActive = useCallback(async () => {
    if (!activeId) { setActive(null); return; }
    try {
      const r = await axios.get(`${API}/cortex/campaigns/${activeId}`,
                                  { withCredentials: true });
      setActive(r.data || null);
    } catch (_e) { setActive(null); }
  }, [activeId]);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { loadActive(); }, [loadActive]);

  // Poll the active campaign while it's still building so the user
  // watches steps complete in real time.
  useEffect(() => {
    if (!active) return undefined;
    const buildingActive = active.status === 'building';
    const hasGenerating = (active.creatives || []).some((c) => c.status === 'generating');
    if (!buildingActive && !hasGenerating) return undefined;
    const id = setInterval(loadActive, 3000);
    return () => clearInterval(id);
  }, [active, loadActive]);

  return (
    <DashboardLayout>
      <div data-testid="campaigns-page" className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-white tracking-tight">Campaigns</h1>
            <p className="text-sm text-zinc-400 mt-1">
              Every campaign Cortex has built from your assets — posts, emails, landing pages, creatives.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="text-zinc-500 text-sm">Loading campaigns…</div>
        ) : active ? (
          <CampaignDetail campaign={active}
                            onBack={() => setSearchParams({})}
                            onChanged={loadActive} />
        ) : campaigns.length === 0 ? (
          <EmptyState />
        ) : (
          <CampaignList campaigns={campaigns}
                          onOpen={(id) => setSearchParams({ id })} />
        )}
      </div>
    </DashboardLayout>
  );
}


function EmptyState() {
  return (
    <div data-testid="campaigns-empty"
          className="rounded-2xl border border-white/5 bg-white/[0.02] p-8 text-center">
      <Rocket size={26} className="text-violet-300 mx-auto mb-2" />
      <div className="text-white font-semibold mb-1">No campaigns yet</div>
      <div className="text-sm text-zinc-400">
        Open an Asset → Creative Brief → click <strong className="text-violet-300">Build full campaign</strong> to spawn a complete asset bundle.
      </div>
    </div>
  );
}


function CampaignList({ campaigns, onOpen }) {
  return (
    <div data-testid="campaigns-list" className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <AnimatePresence>
        {campaigns.map((c) => (
          <motion.button layout key={c.id}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            onClick={() => onOpen(c.id)}
                            data-testid={`campaign-card-${c.id}`}
                            className="text-left rounded-xl border border-violet-500/15 bg-white/[0.02] hover:bg-white/[0.04] p-4 transition">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="w-7 h-7 rounded-md bg-violet-500/15 border border-violet-500/30 text-violet-300 flex items-center justify-center">
                <Rocket size={12} />
              </span>
              <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded border ${STATUS_TONE[c.status] || 'bg-white/5 text-zinc-300 border-white/10'}`}>
                {c.status === 'building'
                  ? <><Loader2 size={9} className="animate-spin inline mr-1" />Building</>
                  : c.status}
              </span>
              <span className="text-[10px] text-zinc-500 ml-auto">{fmtDate(c.created_at)}</span>
            </div>
            <div className="text-base font-semibold text-white truncate">{c.title}</div>
            {c.goal && (
              <div className="text-[12px] text-zinc-400 leading-snug line-clamp-2 mt-1">
                {c.goal}
              </div>
            )}
            <div className="flex items-center gap-1.5 mt-2 text-[11px] text-zinc-500">
              Open <ChevronRight size={10} />
            </div>
          </motion.button>
        ))}
      </AnimatePresence>
    </div>
  );
}


function CampaignDetail({ campaign, onBack, onChanged }) {
  const [tab, setTab] = useState('overview');
  const status = campaign.status || 'building';
  const posts = campaign.social_posts || [];
  const emails = campaign.email_sequence || [];
  const lp = campaign.landing_page || null;
  const creatives = campaign.creatives || [];

  return (
    <div data-testid="campaign-detail" className="space-y-4">
      <button onClick={onBack}
              data-testid="campaign-detail-back"
              className="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition">
        <ArrowLeft size={14} /> Back to all campaigns
      </button>

      {/* Hero */}
      <div className="rounded-2xl border border-violet-500/20 bg-gradient-to-br from-violet-500/[0.06] to-fuchsia-500/[0.02] p-5">
        <div className="flex items-center gap-3 mb-2">
          <span className="w-10 h-10 rounded-lg bg-violet-500/15 border border-violet-500/30 text-violet-300 flex items-center justify-center">
            <Rocket size={16} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-widest text-violet-300 font-semibold">Campaign</div>
            <div className="text-xl font-semibold text-white truncate">{campaign.title}</div>
          </div>
          <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-1 rounded border ${STATUS_TONE[status] || 'bg-white/5 text-zinc-300 border-white/10'}`}>
            {status === 'building'
              ? <><Loader2 size={10} className="animate-spin inline mr-1" />Building</>
              : status}
          </span>
        </div>
        {campaign.goal && (
          <div className="text-[13.5px] text-zinc-200 leading-relaxed mb-1">
            <Target size={11} className="inline mr-1 text-violet-300" /> {campaign.goal}
          </div>
        )}
        {campaign.summary && (
          <div className="text-[12.5px] text-zinc-400 leading-relaxed">{campaign.summary}</div>
        )}
      </div>

      {/* Tab bar */}
      <div data-testid="campaign-tabs" className="flex items-center gap-1.5 flex-wrap border-b border-white/5 pb-2">
        <TabBtn id="overview"  active={tab} onClick={setTab} icon={Sparkles}      label="Overview" />
        <TabBtn id="posts"     active={tab} onClick={setTab} icon={MessageCircle} label={`Posts (${posts.length})`} />
        <TabBtn id="emails"    active={tab} onClick={setTab} icon={Mail}          label={`Emails (${emails.length})`} />
        <TabBtn id="landing"   active={tab} onClick={setTab} icon={Globe}         label="Landing" />
        <TabBtn id="creatives" active={tab} onClick={setTab} icon={ImageIcon}     label={`Creatives (${creatives.length})`} />
      </div>

      {tab === 'overview'  && <OverviewTab campaign={campaign} />}
      {tab === 'posts'     && <PostsTab posts={posts} campaign={campaign} onChanged={onChanged} />}
      {tab === 'emails'    && <EmailsTab emails={emails} />}
      {tab === 'landing'   && <LandingTab lp={lp} />}
      {tab === 'creatives' && <CreativesTab creatives={creatives} />}
    </div>
  );
}


function TabBtn({ id, active, onClick, icon: Icon, label }) {
  const isActive = id === active;
  return (
    <button onClick={() => onClick(id)}
            data-testid={`campaign-tab-${id}`}
            className={`text-[12px] font-semibold px-2.5 py-1.5 rounded-md transition flex items-center gap-1.5 ${
              isActive
                ? 'bg-violet-500/20 text-violet-200 border border-violet-500/40'
                : 'text-zinc-400 hover:text-white hover:bg-white/5 border border-transparent'}`}>
      <Icon size={11} /> {label}
    </button>
  );
}


function OverviewTab({ campaign }) {
  const steps = campaign.steps || [];
  return (
    <div data-testid="campaign-overview" className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
      <div className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold mb-2">Build trace</div>
      <ul className="space-y-1.5">
        {steps.map((s, i) => (
          <li key={i} className="flex items-center gap-2 text-[12.5px]">
            {s.status === 'complete' && <CheckCircle2 size={12} className="text-emerald-300 shrink-0" />}
            {s.status === 'running'  && <Loader2 size={12} className="text-cyan-300 animate-spin shrink-0" />}
            {s.status === 'failed'   && <AlertTriangle size={12} className="text-rose-300 shrink-0" />}
            <span className="text-zinc-200 font-mono">{s.name}</span>
            {s.error && <span className="text-rose-300 text-[11px] ml-2">{s.error}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}


function PostsTab({ posts, campaign, onChanged }) {
  if (posts.length === 0) {
    return <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-sm text-zinc-500">No posts yet.</div>;
  }
  const grouped = posts.reduce((acc, p) => {
    (acc[p.platform || 'other'] = acc[p.platform || 'other'] || []).push(p);
    return acc;
  }, {});
  return (
    <div data-testid="campaign-posts" className="space-y-3">
      <BulkPushBar campaign={campaign} posts={posts} onChanged={onChanged} />
      {Object.entries(grouped).map(([platform, items]) => {
        const tone = PLATFORM_TONE[platform] || 'text-zinc-300 border-white/15 bg-white/[0.04]';
        return (
          <div key={platform} className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
            <div className={`text-[11px] font-semibold px-2 py-0.5 rounded border inline-block mb-3 ${tone}`}>
              {platform}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {items.map((p) => (
                <PostCard key={p.id} post={p} campaign={campaign} onChanged={onChanged} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}


const PUSHABLE = new Set(['facebook', 'instagram', 'instagram_story', 'linkedin', 'pinterest']);
const _normPlatform = (s) => (s || '').trim().toLowerCase().replace(/\s+/g, '_');


function BulkPushBar({ campaign, posts, onChanged }) {
  const [mode, setMode] = useState('draft');           // draft | scheduled
  const [startAt, setStartAt] = useState('');
  const [cadenceHours, setCadenceHours] = useState(24);
  const [pushing, setPushing] = useState(false);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState('');

  const pushable = posts.filter((p) => PUSHABLE.has(_normPlatform(p.platform)));
  const alreadyPushed = pushable.filter((p) => p.pushed_at).length;
  const eligible = pushable.length - alreadyPushed;
  const status = campaign?.status || 'building';
  const disabled = pushing || eligible === 0 || status !== 'complete';

  const push = async () => {
    setPushing(true);
    setErr('');
    setResult(null);
    try {
      const body = { mode };
      if (mode === 'scheduled') {
        if (!startAt) { setErr('Pick a start time'); setPushing(false); return; }
        body.start_at = new Date(startAt).toISOString();
        body.cadence_hours = Number(cadenceHours) || 24;
      }
      const r = await axios.post(
        `${API}/cortex/campaigns/${campaign.id}/push`,
        body, { withCredentials: true });
      setResult(r.data);
      onChanged?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Push failed');
    } finally { setPushing(false); }
  };

  return (
    <div data-testid="bulk-push-bar"
         className="rounded-xl border border-emerald-500/20 bg-gradient-to-br from-emerald-500/[0.05] to-emerald-500/[0.01] p-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="w-7 h-7 rounded-md bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 flex items-center justify-center">
          <Send size={12} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[12.5px] text-white font-semibold">Push to social calendar</div>
          <div className="text-[11px] text-zinc-400">
            {eligible} of {pushable.length} pushable posts ready (Facebook · Instagram · LinkedIn · Pinterest).
            {alreadyPushed > 0 && <span className="text-emerald-300 ml-1">{alreadyPushed} already pushed.</span>}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <label className={`text-[11px] px-2 py-1 rounded border cursor-pointer transition ${mode === 'draft' ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-200' : 'border-white/10 text-zinc-400 hover:text-white'}`}>
            <input type="radio" name="bulk-push-mode" value="draft" checked={mode === 'draft'} onChange={() => setMode('draft')} className="hidden"
                   data-testid="bulk-push-mode-draft" /> Drafts
          </label>
          <label className={`text-[11px] px-2 py-1 rounded border cursor-pointer transition ${mode === 'scheduled' ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-200' : 'border-white/10 text-zinc-400 hover:text-white'}`}>
            <input type="radio" name="bulk-push-mode" value="scheduled" checked={mode === 'scheduled'} onChange={() => setMode('scheduled')} className="hidden"
                   data-testid="bulk-push-mode-scheduled" /> Schedule
          </label>
          <button onClick={push}
                  disabled={disabled}
                  data-testid="bulk-push-submit"
                  className="text-[11.5px] font-bold px-3 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-400 text-emerald-950 disabled:bg-zinc-700 disabled:text-zinc-500 transition flex items-center gap-1.5">
            {pushing
              ? <><Loader2 size={11} className="animate-spin" /> Pushing…</>
              : <><Upload size={11} /> Push {eligible}</>}
          </button>
        </div>
      </div>
      {mode === 'scheduled' && (
        <div className="mt-2 pt-2 border-t border-emerald-500/15 flex items-center gap-2 flex-wrap">
          <label className="text-[11px] text-zinc-400">
            Start at <input type="datetime-local"
                            value={startAt}
                            onChange={(e) => setStartAt(e.target.value)}
                            data-testid="bulk-push-start-at"
                            className="ml-1.5 bg-white/[0.04] border border-white/10 rounded px-2 py-1 text-[11.5px] text-white" />
          </label>
          <label className="text-[11px] text-zinc-400">
            every <input type="number" min={1} max={336}
                          value={cadenceHours}
                          onChange={(e) => setCadenceHours(e.target.value)}
                          data-testid="bulk-push-cadence"
                          className="mx-1.5 w-14 bg-white/[0.04] border border-white/10 rounded px-2 py-1 text-[11.5px] text-white" /> hours
          </label>
        </div>
      )}
      {err && (
        <div className="mt-2 text-[11.5px] text-rose-300 flex items-center gap-1">
          <AlertTriangle size={11} /> {err}
        </div>
      )}
      {result && (
        <div data-testid="bulk-push-result"
             className="mt-2 text-[11.5px] text-emerald-300 flex items-center gap-2">
          <CheckCircle2 size={11} />
          Pushed {result.counts?.pushed || 0} post{(result.counts?.pushed || 0) === 1 ? '' : 's'}.
          {result.counts?.skipped > 0 && <span className="text-zinc-500">({result.counts.skipped} skipped)</span>}
          <a href="/dashboard/marketing-calendar" target="_blank" rel="noreferrer"
             className="text-emerald-200 underline ml-1">Open calendar →</a>
        </div>
      )}
    </div>
  );
}


function PostCard({ post, campaign, onChanged }) {
  const [copied, setCopied] = useState(false);
  const [pushing, setPushing] = useState(false);
  const [pushErr, setPushErr] = useState('');
  const copy = async () => {
    try {
      const text = [post.headline, post.body, (post.hashtags || []).join(' '), post.cta]
        .filter(Boolean).join('\n\n');
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch (_e) { /* */ }
  };
  const platformNorm = _normPlatform(post.platform);
  const pushable = PUSHABLE.has(platformNorm) && campaign?.status === 'complete';
  const alreadyPushed = !!post.pushed_at;
  const push = async () => {
    if (pushing) return;
    setPushing(true);
    setPushErr('');
    try {
      await axios.post(
        `${API}/cortex/campaigns/${campaign.id}/posts/${post.id}/push`,
        { mode: 'draft' }, { withCredentials: true });
      onChanged?.();
    } catch (e) {
      setPushErr(e?.response?.data?.detail || 'Push failed');
    } finally { setPushing(false); }
  };
  return (
    <div data-testid={`post-${post.id}`}
          className="rounded-md bg-white/[0.02] border border-white/5 p-2.5">
      {post.headline && (
        <div className="text-[12.5px] text-white font-semibold leading-snug mb-1">{post.headline}</div>
      )}
      <div className="text-[12px] text-zinc-200 leading-relaxed whitespace-pre-wrap">{post.body}</div>
      {post.hashtags?.length > 0 && (
        <div className="text-[11px] text-cyan-300 mt-2 leading-snug">
          {post.hashtags.map((h, i) => <span key={i} className="mr-1">#{h.replace(/^#/, '')}</span>)}
        </div>
      )}
      <div className="flex items-center gap-2 mt-2 pt-2 border-t border-white/5">
        {post.cta && (
          <span className="text-[10.5px] uppercase tracking-wider text-violet-300 font-bold">
            CTA: {post.cta}
          </span>
        )}
        <div className="flex-1" />
        {alreadyPushed ? (
          <span data-testid={`post-pushed-${post.id}`}
                className="text-[10.5px] font-bold text-emerald-300 flex items-center gap-1">
            <CheckCircle2 size={10} /> Pushed
          </span>
        ) : pushable && (
          <button onClick={push}
                  disabled={pushing}
                  data-testid={`post-push-${post.id}`}
                  className="text-[10.5px] font-bold text-emerald-300 hover:text-emerald-200 transition flex items-center gap-1 disabled:opacity-50">
            {pushing
              ? <><Loader2 size={9} className="animate-spin" /> Pushing…</>
              : <><Upload size={9} /> Push as draft</>}
          </button>
        )}
        <button onClick={copy}
                data-testid={`post-copy-${post.id}`}
                className="text-[10.5px] font-semibold text-zinc-400 hover:text-white transition">
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>
      {pushErr && (
        <div className="mt-1.5 text-[10.5px] text-rose-300 flex items-center gap-1">
          <AlertTriangle size={9} /> {pushErr}
        </div>
      )}
    </div>
  );
}


function EmailsTab({ emails }) {
  if (emails.length === 0) {
    return <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-sm text-zinc-500">No emails yet.</div>;
  }
  return (
    <div data-testid="campaign-emails" className="space-y-2">
      {emails.map((e) => (
        <div key={e.id} data-testid={`email-${e.id}`}
              className="rounded-xl border border-emerald-500/15 bg-emerald-500/[0.03] p-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="w-6 h-6 rounded-md bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 flex items-center justify-center text-[10px] font-bold">
              {e.step}
            </span>
            <span className="text-[10px] uppercase tracking-wider text-emerald-300 font-bold">{e.purpose}</span>
          </div>
          <div className="text-[13.5px] text-white font-semibold">{e.subject}</div>
          {e.preheader && <div className="text-[11.5px] text-zinc-500 italic">{e.preheader}</div>}
          <div className="text-[12px] text-zinc-200 leading-relaxed whitespace-pre-wrap mt-2">{e.body}</div>
          {e.cta && (
            <div className="mt-2 text-[10.5px] uppercase tracking-wider text-emerald-300 font-bold">
              CTA: {e.cta}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}


function LandingTab({ lp }) {
  if (!lp) {
    return <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-sm text-zinc-500">No landing page outline yet.</div>;
  }
  return (
    <div data-testid="campaign-landing" className="rounded-xl border border-amber-500/15 bg-amber-500/[0.03] p-5">
      <div className="text-[10px] uppercase tracking-widest text-amber-300 font-semibold mb-2">Landing page outline</div>
      <div className="text-2xl font-semibold text-white leading-tight">{lp.headline}</div>
      {lp.subheadline && (
        <div className="text-[14px] text-zinc-300 leading-relaxed mt-1">{lp.subheadline}</div>
      )}
      <div className="space-y-2 mt-4">
        {(lp.sections || []).map((s, i) => (
          <div key={i} className="rounded-lg bg-white/[0.02] border border-white/5 p-3">
            <div className="text-[10px] uppercase tracking-wider text-amber-300 font-semibold mb-1">
              {s.title}{s.purpose ? ` · ${s.purpose}` : ''}
            </div>
            <div className="text-[12.5px] text-zinc-200 leading-relaxed">{s.body}</div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 mt-4 pt-3 border-t border-white/5">
        {lp.primary_cta && (
          <span className="text-[11.5px] font-bold text-white px-3 py-1.5 rounded-md bg-gradient-to-r from-amber-500 to-amber-400 shadow">
            {lp.primary_cta}
          </span>
        )}
        {lp.secondary_cta && (
          <span className="text-[11px] text-zinc-300 px-2 py-1 rounded-md bg-white/[0.04] border border-white/10">
            {lp.secondary_cta}
          </span>
        )}
      </div>
    </div>
  );
}


function CreativesTab({ creatives }) {
  if (creatives.length === 0) {
    return <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-sm text-zinc-500">
      Images are queued — they'll appear here as each one finishes (~30-60s each).
    </div>;
  }
  return (
    <div data-testid="campaign-creatives" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
      {creatives.map((c) => {
        const tone = c.provider === 'openai'
          ? 'text-emerald-300 bg-emerald-500/15 border-emerald-500/30'
          : 'text-fuchsia-300 bg-fuchsia-500/15 border-fuchsia-500/30';
        const src = c.file_url ? (c.file_url.startsWith('http')
          ? c.file_url
          : `${process.env.REACT_APP_BACKEND_URL}${c.file_url}`) : null;
        return (
          <div key={c.id} className="rounded-md bg-violet-500/[0.05] border border-violet-500/15 p-2">
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className="text-[12px] text-zinc-100 font-semibold truncate">{c.concept_title}</span>
              {c.provider && (
                <span className={`text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded border ${tone} ml-auto`}>
                  {c.provider}
                </span>
              )}
            </div>
            {c.status === 'complete' && src && (
              <img src={src} alt={c.concept_title}
                    data-testid={`campaign-creative-${c.id}`}
                    className="w-full aspect-square object-cover rounded border border-white/5" />
            )}
            {c.status === 'generating' && (
              <div className="aspect-square rounded border border-violet-500/20 bg-violet-500/[0.05] flex flex-col items-center justify-center text-violet-300">
                <Loader2 size={20} className="animate-spin mb-1" />
                <span className="text-[11px]">Generating…</span>
              </div>
            )}
            {c.status === 'failed' && (
              <div className="aspect-square rounded border border-rose-500/30 bg-rose-500/[0.06] flex items-center justify-center text-[11px] text-rose-200 p-2 text-center">
                <AlertTriangle size={12} className="inline mr-1" />
                Generation failed
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}


function fmtDate(v) {
  if (!v) return '';
  try {
    return new Date(v).toLocaleString(undefined,
      { dateStyle: 'medium', timeStyle: 'short' });
  } catch (_e) { return ''; }
}
