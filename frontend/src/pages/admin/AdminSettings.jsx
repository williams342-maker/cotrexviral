import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import {
  Loader2, UserCheck, UserX, ShieldAlert, Save, Power, RotateCcw,
  Instagram, Twitter, Facebook, Linkedin, Youtube,
} from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

// Curated set of social platforms — matches the SUPPORTED_PLATFORMS in
// /app/backend/routes/channels.py. We expose a friendly subset (the social
// channels users actually toggle on/off); the full catalog stays in code.
const PLATFORMS = [
  { id: 'instagram', label: 'Instagram', icon: Instagram, color: 'text-pink-500' },
  { id: 'tiktok', label: 'TikTok', icon: () => <span className="text-xs font-black">T</span>, color: 'text-neutral-900' },
  { id: 'x', label: 'X (Twitter)', icon: Twitter, color: 'text-neutral-700' },
  { id: 'facebook', label: 'Facebook', icon: Facebook, color: 'text-blue-600' },
  { id: 'linkedin', label: 'LinkedIn', icon: Linkedin, color: 'text-sky-700' },
  { id: 'youtube', label: 'YouTube', icon: Youtube, color: 'text-red-600' },
  { id: 'pinterest', label: 'Pinterest', icon: () => <span className="text-xs font-black">P</span>, color: 'text-red-500' },
  { id: 'threads', label: 'Threads', icon: () => <span className="text-xs font-black">@</span>, color: 'text-neutral-800' },
  { id: 'reddit', label: 'Reddit', icon: () => <span className="text-xs font-black">R</span>, color: 'text-orange-600' },
];

const AdminSettings = () => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [signupsEnabled, setSignupsEnabled] = useState(true);
  const [disabled, setDisabled] = useState(() => new Set());
  const [initial, setInitial] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/settings`, { withCredentials: true });
      setSignupsEnabled(r.data.signups_enabled);
      setDisabled(new Set(r.data.disabled_platforms || []));
      setInitial({
        signups_enabled: r.data.signups_enabled,
        disabled_platforms: r.data.disabled_platforms || [],
      });
    } catch (e) {
      toast({ title: 'Could not load settings' });
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const togglePlatform = (id) => {
    setDisabled((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      const r = await axios.patch(
        `${API}/admin/settings`,
        {
          signups_enabled: signupsEnabled,
          disabled_platforms: Array.from(disabled),
        },
        { withCredentials: true },
      );
      setInitial({
        signups_enabled: r.data.signups_enabled,
        disabled_platforms: r.data.disabled_platforms || [],
      });
      toast({ title: 'Settings saved', description: 'Live across the platform within a few seconds.' });
    } catch (e) {
      toast({ title: 'Could not save', description: e.response?.data?.detail });
    }
    setSaving(false);
  };

  const dirty = initial && (
    initial.signups_enabled !== signupsEnabled
    || initial.disabled_platforms.length !== disabled.size
    || initial.disabled_platforms.some((p) => !disabled.has(p))
  );

  const reset = () => {
    if (!initial) return;
    setSignupsEnabled(initial.signups_enabled);
    setDisabled(new Set(initial.disabled_platforms));
  };

  if (loading) {
    return (
      <DashboardLayout title="System Settings"><div className="text-center py-12">
        <Loader2 className="animate-spin text-[#1B7BFF] mx-auto" />
      </div></DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      title="System Settings"
      subtitle="Master switches for signups and per-platform integrations."
    >
      {/* Signups toggle */}
      <section className="mb-7" data-testid="admin-signups-section">
        <div className="bg-white rounded-3xl p-6 border border-neutral-200/70">
          <div className="flex items-start gap-4">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${
              signupsEnabled ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
            }`}>
              {signupsEnabled ? <UserCheck size={22} /> : <UserX size={22} />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[15px] font-semibold text-neutral-900">Accept new users</div>
              <p className="text-[13px] text-neutral-600 mt-0.5 leading-relaxed">
                {signupsEnabled
                  ? 'Anyone with a Google account can sign up for CortexViral right now.'
                  : 'Brand-new Google signups are paused. Existing users can still log in, and admins can still create accounts manually from the Users page.'}
              </p>
              {!signupsEnabled && (
                <div className="mt-2 inline-flex items-center gap-1.5 text-[11.5px] font-semibold text-rose-700 bg-rose-50 border border-rose-200 px-2.5 py-1 rounded-full" data-testid="signups-paused-badge">
                  <ShieldAlert size={11} /> SIGNUPS PAUSED
                </div>
              )}
            </div>
            <ToggleSwitch
              checked={signupsEnabled}
              onChange={() => setSignupsEnabled((v) => !v)}
              testId="signups-toggle"
            />
          </div>
        </div>
      </section>

      {/* Per-platform toggles */}
      <section data-testid="admin-platforms-section">
        <div className="bg-white rounded-3xl p-6 border border-neutral-200/70">
          <div className="flex items-start gap-3 mb-5">
            <div className="w-12 h-12 rounded-xl bg-violet-50 text-violet-700 flex items-center justify-center shrink-0">
              <Power size={20} />
            </div>
            <div>
              <div className="text-[15px] font-semibold text-neutral-900">Integration kill-switches</div>
              <p className="text-[13px] text-neutral-600 mt-0.5 leading-relaxed">
                Turn off any platform globally. Existing connections stay intact (so scheduled posts aren't broken), but no new connects will succeed until you flip it back on.
              </p>
            </div>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {PLATFORMS.map((p) => {
              const Icon = p.icon;
              const isOff = disabled.has(p.id);
              return (
                <div
                  key={p.id}
                  data-testid={`platform-row-${p.id}`}
                  className={`flex items-center gap-3 p-3.5 rounded-2xl border transition-colors ${
                    isOff
                      ? 'bg-rose-50/50 border-rose-200'
                      : 'bg-neutral-50/40 border-neutral-200/70'
                  }`}
                >
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 bg-white border border-neutral-200/70 ${p.color}`}>
                    <Icon size={15} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[13.5px] font-semibold text-neutral-900">{p.label}</div>
                    <div className={`text-[11px] font-medium mt-0.5 ${isOff ? 'text-rose-700' : 'text-emerald-700'}`}>
                      {isOff ? 'Disabled' : 'Enabled'}
                    </div>
                  </div>
                  <ToggleSwitch
                    checked={!isOff}
                    onChange={() => togglePlatform(p.id)}
                    testId={`platform-toggle-${p.id}`}
                    small
                  />
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Sticky action bar */}
      {dirty && (
        <div
          data-testid="admin-settings-action-bar"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-neutral-900 text-white rounded-2xl shadow-2xl px-5 py-3 flex items-center gap-3 border border-neutral-700"
        >
          <span className="text-[13px] font-semibold">Unsaved changes</span>
          <button
            onClick={reset}
            disabled={saving}
            data-testid="admin-settings-discard"
            className="inline-flex items-center gap-1.5 text-[12.5px] font-medium px-3 h-9 rounded-lg hover:bg-neutral-800 text-neutral-300 disabled:opacity-50"
          >
            <RotateCcw size={12} /> Discard
          </button>
          <button
            onClick={save}
            disabled={saving}
            data-testid="admin-settings-save"
            className="inline-flex items-center gap-1.5 bg-emerald-500 hover:bg-emerald-400 text-white text-[12.5px] font-semibold px-4 h-9 rounded-lg disabled:opacity-50"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      )}
    </DashboardLayout>
  );
};

const ToggleSwitch = ({ checked, onChange, testId, small = false }) => {
  const w = small ? 'w-10 h-6' : 'w-12 h-7';
  const knob = small ? 'w-4 h-4' : 'w-5 h-5';
  const shift = small ? (checked ? 'translate-x-4' : 'translate-x-0.5') : (checked ? 'translate-x-5' : 'translate-x-0.5');
  return (
    <button
      type="button"
      onClick={onChange}
      data-testid={testId}
      aria-pressed={checked}
      className={`relative ${w} rounded-full transition-colors shrink-0 ${
        checked ? 'bg-emerald-500' : 'bg-neutral-300'
      }`}
    >
      <span
        className={`absolute top-1/2 -translate-y-1/2 ${knob} bg-white rounded-full shadow-md transition-transform ${shift}`}
      />
    </button>
  );
};

export default AdminSettings;
