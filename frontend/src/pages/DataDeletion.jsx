import React, { useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { Loader2, Trash2, ShieldAlert, CheckCircle2, Mail } from 'lucide-react';
import CVNavbar from '../components/cv/CVNavbar';
import CVBackdrop from '../components/cv/CVBackdrop';
import CVFooter from '../components/cv/CVFooter';
import CVSeo, { buildBreadcrumbSchema } from '../components/cv/CVSeo';
import CVBreadcrumbs from '../components/cv/CVBreadcrumbs';
import { useAuth, API } from '../context/AuthContext';
import { useToast } from '../hooks/use-toast';

/* /data-deletion — public, GDPR + Meta/TikTok app-review-friendly page that
   spells out exactly how a user (or non-user, e.g. someone whose Facebook
   data we received via a connected channel) can delete every byte we hold
   about them. The in-page "Delete my account" CTA self-serves authenticated
   users; unauthenticated visitors get the email-based path. */
const DataDeletion = () => {
  const { user, logout } = useAuth();
  const { toast } = useToast();
  const [showConfirm, setShowConfirm] = useState(false);

  return (
    <div className="min-h-screen cv-dark antialiased text-zinc-100 relative overflow-x-hidden">
      <CVSeo
        title="Data Deletion — CortexViral"
        description="Delete your CortexViral account and all associated data — self-serve in-app, or email privacy@cortexviral.com."
        path="/data-deletion"
        schema={buildBreadcrumbSchema([
          { name: 'Home', path: '/' },
          { name: 'Data Deletion', path: '/data-deletion' },
        ])}
      />
      <CVNavbar />
      <section className="relative pt-32 pb-24 overflow-hidden">
        <CVBackdrop variant="hero" />
        <main className="relative z-10">
          <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <CVBreadcrumbs items={[
            { label: 'Legal', to: '/sitemap' },
            { label: 'Data Deletion' },
          ]} className="mb-5" />
          <h1 className="text-[44px] md:text-[56px] leading-[1.02] font-medium tracking-tight mt-6">
            Delete <span className="bg-clip-text text-transparent bg-gradient-to-r from-rose-300 via-fuchsia-300 to-violet-300">your data</span>
          </h1>
          <p className="text-[15px] md:text-[16px] text-zinc-400 mt-4 leading-relaxed max-w-2xl">
            You own your data. Deleting your account removes <strong className="text-zinc-200">every piece</strong> of information we hold about you — and revokes our access to any social channel you connected through CortexViral. This action is permanent and cannot be undone.
          </p>

          {/* Self-serve in-app delete */}
          <section className="mt-10 cv-glass rounded-3xl p-7" data-testid="data-deletion-self-serve">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center shrink-0">
                <Trash2 className="text-rose-300" size={20} />
              </div>
              <div className="flex-1">
                <div className="text-[11px] uppercase tracking-[0.18em] text-rose-300/80 font-semibold mb-1">Option 1 — In-app</div>
                <h2 className="text-[20px] font-semibold tracking-tight text-white">Delete my account right now</h2>
                <p className="text-[13.5px] text-zinc-400 mt-1 leading-relaxed">
                  {user
                    ? 'You are signed in. Tap below to permanently delete your CortexViral account and all related data.'
                    : 'Sign in first, then come back to this page (or visit Settings → Delete account) to remove everything in one click.'}
                </p>
                <button
                  type="button"
                  data-testid="data-deletion-trigger"
                  disabled={!user}
                  onClick={() => setShowConfirm(true)}
                  className="mt-4 inline-flex items-center gap-2 bg-rose-500 hover:bg-rose-400 text-white text-[13px] font-semibold px-5 h-11 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Trash2 size={14} /> {user ? 'Delete my account' : 'Sign in to delete'}
                </button>
                {!user && (
                  <Link to="/" className="ml-2 text-[12.5px] text-cyan-300 hover:text-cyan-200 font-medium">Sign in →</Link>
                )}
              </div>
            </div>
          </section>

          {/* Email-based delete */}
          <section className="mt-5 cv-glass rounded-3xl p-7" data-testid="data-deletion-email">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl bg-violet-500/10 border border-violet-500/30 flex items-center justify-center shrink-0">
                <Mail className="text-violet-300" size={20} />
              </div>
              <div className="flex-1">
                <div className="text-[11px] uppercase tracking-[0.18em] text-violet-300/80 font-semibold mb-1">Option 2 — Email</div>
                <h2 className="text-[20px] font-semibold tracking-tight text-white">Email our privacy team</h2>
                <p className="text-[13.5px] text-zinc-400 mt-1 leading-relaxed">
                  Don't have access to the app, or want a record of the request? Email{' '}
                  <a href="mailto:privacy@cortexviral.com?subject=Data%20deletion%20request" className="text-cyan-300 font-medium hover:underline">privacy@cortexviral.com</a> with the subject{' '}
                  <em className="text-zinc-300">"Data deletion request"</em> and the email address you signed up with. We'll confirm receipt within 2 business days and complete the deletion within 30 days, as required by GDPR.
                </p>
              </div>
            </div>
          </section>

          {/* What gets deleted */}
          <section className="mt-12">
            <h2 className="text-[24px] font-medium tracking-tight text-white mb-4">What gets deleted</h2>
            <ul className="space-y-2.5 text-[14px] text-zinc-300 leading-relaxed list-disc pl-5 marker:text-rose-400">
              <li>Your <strong>account</strong> — email, name, profile picture, onboarding profile (brand, niche, goals).</li>
              <li>Every <strong>post</strong> you've published or scheduled through CortexViral (including recurrence series).</li>
              <li>Every <strong>AI generation</strong> we ran for you (drafts, hooks, captions, SEO reports, video scripts).</li>
              <li>Every <strong>lead</strong> you submitted via the "Choose Your Specialist" form.</li>
              <li>All <strong>OAuth tokens</strong> for social channels you connected (LinkedIn, TikTok, etc.). We also revoke these tokens with the upstream providers where supported.</li>
              <li>All <strong>support tickets</strong> and ticket messages you authored.</li>
              <li>All <strong>active and historical sessions</strong> + magic-link tokens.</li>
            </ul>
          </section>

          {/* Retention exceptions */}
          <section className="mt-12">
            <h2 className="text-[24px] font-medium tracking-tight text-white mb-4">What we retain (and why)</h2>
            <p className="text-[14px] text-zinc-400 leading-relaxed mb-3">
              A small set of records is preserved for legal and accounting compliance — these contain no content you authored:
            </p>
            <ul className="space-y-2.5 text-[14px] text-zinc-300 leading-relaxed list-disc pl-5 marker:text-zinc-500">
              <li><strong>Payment / invoice records</strong> retained for 7 years (required by tax law). Held by Stripe, not by CortexViral.</li>
              <li><strong>Deletion audit row</strong> — a single row in <code className="text-cyan-300 text-[12px]">account_deletions</code> with your user ID, email, request timestamp, and reason (if you provided one). Kept indefinitely as proof we honoured your request.</li>
              <li><strong>Anonymous aggregate analytics</strong> — pageview counts with no link back to you.</li>
            </ul>
          </section>

          {/* Meta / TikTok app-review specific instructions */}
          <section className="mt-12 cv-glass rounded-3xl p-7" data-testid="data-deletion-platforms">
            <div className="flex items-start gap-3 mb-3">
              <ShieldAlert size={18} className="text-amber-300 shrink-0 mt-0.5" />
              <h2 className="text-[18px] font-semibold tracking-tight text-white">Data we received from Facebook, Instagram, or TikTok</h2>
            </div>
            <p className="text-[13.5px] text-zinc-400 leading-relaxed">
              When you connect a social channel, the platform sends us an OAuth token + basic profile info (display name, picture, platform user ID). To revoke this data specifically:
            </p>
            <ol className="space-y-2 text-[13.5px] text-zinc-300 leading-relaxed mt-3 list-decimal pl-5 marker:text-amber-300/80">
              <li>Sign in to CortexViral → <Link to="/dashboard/channels" className="text-cyan-300 hover:underline">Integrations</Link> → click <strong>Disconnect</strong> on the relevant platform.</li>
              <li>OR delete the entire account using Option 1 above — every connection is revoked automatically.</li>
              <li>OR remove CortexViral directly from the source platform: Facebook → Settings → Apps and Websites; Instagram → Settings → Apps and Websites; TikTok → Settings → Manage app permissions.</li>
            </ol>
          </section>

          {/* Footer note */}
          <p className="mt-12 text-[12.5px] text-zinc-500 leading-relaxed">
            This page is the official endpoint for data-deletion requests under GDPR, CCPA, and the Meta Platform / TikTok Developer policies. Questions or appeals — <a href="mailto:privacy@cortexviral.com" className="text-zinc-300 hover:text-white">privacy@cortexviral.com</a>.
          </p>
          </div>
        </main>
      </section>
      <CVFooter />

      {showConfirm && user && (
        <ConfirmDeleteModal
          email={user.email}
          onClose={() => setShowConfirm(false)}
          onConfirmed={async () => {
            try { await logout(); } catch (e) { /* already cleared server-side */ }
            toast({ title: 'Account deleted', description: 'All your data has been removed. Goodbye for now.' });
            window.location.href = '/';
          }}
        />
      )}
    </div>
  );
};

const ConfirmDeleteModal = ({ email, onClose, onConfirmed }) => {
  const { toast } = useToast();
  const [phrase, setPhrase] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const required = 'DELETE MY ACCOUNT';

  const submit = async (e) => {
    e.preventDefault();
    if (phrase !== required) {
      toast({ title: 'Type the phrase exactly to continue' });
      return;
    }
    setBusy(true);
    try {
      await axios.post(`${API}/account/delete`, { confirmation: phrase, reason }, { withCredentials: true });
      onConfirmed();
    } catch (err) {
      toast({
        title: 'Could not delete account',
        description: err.response?.data?.detail || err.message,
      });
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={() => { if (!busy) onClose(); }}
      data-testid="data-deletion-confirm-modal"
    >
      <div
        className="bg-zinc-950 border border-rose-500/30 rounded-3xl max-w-md w-full p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 text-rose-300 mb-1">
          <ShieldAlert size={20} />
          <h3 className="text-lg font-semibold">Permanently delete account</h3>
        </div>
        <p className="text-[13.5px] text-zinc-400 leading-relaxed mt-2">
          You're about to delete <strong className="text-white">{email}</strong> and every piece of data tied to it. This cannot be undone. Type <code className="text-rose-300 bg-rose-500/10 px-1.5 py-0.5 rounded text-[12px]">{required}</code> to confirm.
        </p>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <input
            type="text"
            value={phrase}
            onChange={(e) => setPhrase(e.target.value)}
            placeholder={required}
            data-testid="data-deletion-confirm-input"
            autoFocus
            className="w-full h-11 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-100 px-3.5 text-[13.5px] font-mono outline-none focus:border-rose-500/50"
          />
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            placeholder="(Optional) Tell us why you're leaving — it helps us improve."
            data-testid="data-deletion-confirm-reason"
            className="w-full rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-100 px-3.5 py-2.5 text-[13px] outline-none focus:border-rose-500/50 resize-none"
          />
          <div className="flex gap-2 justify-end pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="text-[13px] font-medium text-zinc-300 px-4 h-10 rounded-xl hover:bg-zinc-800/80"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy || phrase !== required}
              data-testid="data-deletion-confirm-submit"
              className="inline-flex items-center gap-2 bg-rose-500 hover:bg-rose-400 disabled:opacity-40 text-white text-[13px] font-semibold px-5 h-10 rounded-xl"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
              {busy ? 'Deleting…' : 'Delete forever'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default DataDeletion;
