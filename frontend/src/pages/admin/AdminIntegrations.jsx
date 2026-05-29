import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, Save, Trash2, KeyRound, Database, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* Admin Integrations — DB-backed runtime config.
   Lets an admin rotate Meta (and future) API keys without a redeploy.
   Resolves DB → env → default; secrets are masked in the UI. */
const SOURCE_LABELS = {
  database:    { text: 'Database', color: 'text-violet-700 bg-violet-50 border-violet-200' },
  environment: { text: 'Env File',  color: 'text-amber-700 bg-amber-50 border-amber-200' },
  unset:       { text: 'Unset',     color: 'text-neutral-500 bg-neutral-100 border-neutral-200' },
};

const AdminIntegrations = () => {
  const { toast } = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [drafts, setDrafts] = useState({});      // key → string user is typing
  const [saving, setSaving] = useState({});      // key → bool

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/app-config`, { withCredentials: true });
      setItems(r.data.items || []);
    } catch (e) {
      toast({ title: 'Failed to load integrations', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const save = async (key) => {
    setSaving((s) => ({ ...s, [key]: true }));
    try {
      const value = drafts[key] ?? '';
      const r = await axios.put(`${API}/admin/app-config`,
        { key, value },
        { withCredentials: true },
      );
      toast({
        title: r.data.cleared ? `${key} cleared` : `${key} saved`,
        description: r.data.cleared
          ? 'Falling back to env var / default.'
          : 'Active within 60s (cache TTL). Restart not required.',
      });
      setDrafts((d) => { const cp = { ...d }; delete cp[key]; return cp; });
      await load();
    } catch (e) {
      toast({ title: 'Save failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setSaving((s) => ({ ...s, [key]: false }));
    }
  };

  const remove = async (key) => {
    if (!window.confirm(`Clear ${key}? It will fall back to the env var (if any).`)) return;
    setSaving((s) => ({ ...s, [key]: true }));
    try {
      await axios.delete(`${API}/admin/app-config/${key}`, { withCredentials: true });
      toast({ title: `${key} removed`, description: 'Active within 60s.' });
      await load();
    } catch (e) {
      toast({ title: 'Delete failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setSaving((s) => ({ ...s, [key]: false }));
    }
  };

  // Group by `group` (currently only "meta", but designed for more).
  const groups = items.reduce((acc, it) => {
    acc[it.group] = acc[it.group] || [];
    acc[it.group].push(it);
    return acc;
  }, {});

  return (
    <DashboardLayout title="Integrations" subtitle="Rotate API credentials live — no redeploy required.">
      <div className="space-y-8" data-testid="admin-integrations-page">

        {/* Header banner */}
        <div className="rounded-2xl border border-violet-200/60 bg-gradient-to-br from-violet-50 via-white to-violet-50 p-5 flex items-start gap-4">
          <span className="w-10 h-10 rounded-xl bg-violet-100 text-violet-700 flex items-center justify-center shrink-0">
            <Database size={18} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-widest text-violet-600 font-bold mb-1">Runtime config</div>
            <div className="text-[13.5px] text-neutral-800 leading-relaxed">
              Keys saved here take effect within 60 seconds (cache TTL). Resolution order: <strong>database → environment → default</strong>.
              Secret values are masked once saved. Empty input clears the DB value (falls back to env).
            </div>
          </div>
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-neutral-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>
        )}

        {!loading && Object.entries(groups).map(([groupName, groupItems]) => (
          <section key={groupName} className="space-y-4" data-testid={`group-${groupName}`}>
            <div className="flex items-center gap-3">
              <h2 className="text-base font-semibold text-neutral-900 uppercase tracking-wider">{groupName}</h2>
              <span className="text-[11px] text-neutral-500 tabular-nums">
                {groupItems.filter((i) => i.is_set).length} / {groupItems.length} set
              </span>
            </div>

            <div className="bg-white rounded-2xl border border-neutral-200/70 divide-y divide-neutral-100">
              {groupItems.map((item) => {
                const draft = drafts[item.key];
                const dirty = draft !== undefined && draft !== '';
                const sourceMeta = SOURCE_LABELS[item.source] || SOURCE_LABELS.unset;
                return (
                  <div key={item.key} className="p-4" data-testid={`config-row-${item.key}`}>
                    <div className="flex items-start gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <code className="text-[12px] font-mono font-bold text-neutral-900 bg-neutral-100 px-1.5 py-0.5 rounded">
                            {item.key}
                          </code>
                          <span className={`text-[10px] uppercase tracking-widest px-1.5 py-0.5 rounded border font-bold ${sourceMeta.color}`}>
                            {sourceMeta.text}
                          </span>
                          {item.secret && (
                            <span className="text-[10px] uppercase tracking-widest px-1.5 py-0.5 rounded border border-rose-200 bg-rose-50 text-rose-700 font-bold flex items-center gap-1">
                              <KeyRound size={9} /> SECRET
                            </span>
                          )}
                          {item.is_set ? (
                            <CheckCircle2 size={14} className="text-emerald-600" />
                          ) : (
                            <AlertCircle size={14} className="text-amber-500" />
                          )}
                        </div>
                        <div className="text-[12.5px] text-neutral-600 leading-relaxed mb-2">{item.description}</div>
                        {item.is_set && (
                          <div className="text-[11px] text-neutral-500 tabular-nums mb-2">
                            Current: <code className="font-mono bg-neutral-50 px-1 py-0.5 rounded text-neutral-700">{item.preview || '(empty)'}</code>
                            {item.updated_by && <span className="ml-3 text-neutral-400">· last set by {item.updated_by}</span>}
                          </div>
                        )}
                        <div className="flex items-center gap-2">
                          <input
                            type={item.secret ? 'password' : 'text'}
                            placeholder={item.is_set ? 'Enter a new value to overwrite…' : 'Enter value…'}
                            value={draft ?? ''}
                            onChange={(e) => setDrafts({ ...drafts, [item.key]: e.target.value })}
                            className="flex-1 text-[13px] font-mono px-3 py-2 rounded-lg border border-neutral-300 focus:border-violet-500 focus:ring-1 focus:ring-violet-500 outline-none"
                            data-testid={`input-${item.key}`}
                          />
                          <button
                            onClick={() => save(item.key)}
                            disabled={!dirty || saving[item.key]}
                            className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
                            data-testid={`save-${item.key}`}
                          >
                            {saving[item.key] ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                            Save
                          </button>
                          {item.source === 'database' && (
                            <button
                              onClick={() => remove(item.key)}
                              disabled={saving[item.key]}
                              className="text-[12px] font-semibold px-2.5 py-2 rounded-lg border border-neutral-300 text-neutral-600 hover:bg-neutral-100 disabled:opacity-40 disabled:cursor-not-allowed"
                              title="Clear DB value (falls back to env)"
                              data-testid={`clear-${item.key}`}
                            >
                              <Trash2 size={13} />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ))}

        {!loading && items.length === 0 && (
          <div className="text-center py-12 text-neutral-500">
            No configurable keys exposed yet.
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default AdminIntegrations;
