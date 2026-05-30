import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, Users, Sparkles, Send, CheckCircle2, ShieldAlert, RefreshCw } from 'lucide-react';

const STAGE_TONE = {
  discovered:   'bg-cyan-50 text-cyan-700 border-cyan-100',
  qualified:    'bg-violet-50 text-violet-700 border-violet-100',
  outreached:   'bg-sky-50 text-sky-700 border-sky-100',
  interested:   'bg-amber-50 text-amber-700 border-amber-100',
  onboarding:   'bg-blue-50 text-blue-700 border-blue-100',
  active:       'bg-emerald-50 text-emerald-700 border-emerald-100',
  churned:      'bg-rose-50 text-rose-700 border-rose-100',
  unresponsive: 'bg-neutral-100 text-neutral-700 border-neutral-200',
};

const AdminSellerOS = () => {
  const [funnel, setFunnel] = useState(null);
  const [leads, setLeads] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [stageFilter, setStageFilter] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [f, l, w] = await Promise.all([
        axios.get(`${API}/admin/seller-os/funnel`,    { withCredentials: true }),
        axios.get(`${API}/admin/seller-os/leads?limit=200${stageFilter ? `&stage=${stageFilter}` : ''}`,
          { withCredentials: true }),
        axios.get(`${API}/admin/seller-os/workflows?limit=100`, { withCredentials: true }),
      ]);
      setFunnel(f.data);
      setLeads(l.data?.leads || []);
      setWorkflows(w.data?.workflows || []);
    } catch { /* keep page silent — error is visible via empty state */ }
    finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [stageFilter]);

  const STAGES = ['discovered', 'qualified', 'outreached', 'interested',
                   'onboarding', 'active', 'churned', 'unresponsive'];

  return (
    <DashboardLayout
      title="Admin · Seller-OS"
      subtitle="Cross-user inspector for every seller-acquisition mission, lead, and retention workflow."
      headerExtra={
        <button onClick={load} disabled={loading}
                data-testid="admin-seller-os-refresh"
                className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-neutral-900 text-white hover:bg-neutral-700 transition flex items-center gap-1.5 disabled:opacity-50">
          {loading ? <Loader2 className="animate-spin" size={13} /> : <RefreshCw size={13} />}
          Refresh
        </button>
      }
    >
      <div className="space-y-6" data-testid="admin-seller-os-page">
        {/* Funnel snapshot */}
        <div className="bg-white rounded-2xl border border-neutral-200/70 p-5">
          <div className="text-[11px] uppercase tracking-wider text-neutral-500 font-semibold mb-3">
            Stage waterfall · all users
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {STAGES.map((s) => (
              <button key={s} onClick={() => setStageFilter(stageFilter === s ? '' : s)}
                      data-testid={`admin-seller-os-stage-${s}`}
                      className={`text-left rounded-xl border p-3 transition ${
                        stageFilter === s ? STAGE_TONE[s] : 'bg-neutral-50 text-neutral-700 border-neutral-200/70 hover:bg-neutral-100'
                      }`}>
                <div className="text-[10.5px] uppercase tracking-wider font-semibold opacity-80">{s}</div>
                <div className="text-2xl font-medium tabular-nums">{funnel?.funnel?.[s] || 0}</div>
              </button>
            ))}
          </div>
          <div className="text-[11.5px] text-neutral-500 mt-3">
            Total: <strong className="text-neutral-900">{funnel?.total || 0}</strong>
            {stageFilter && <> · filtering by <strong>{stageFilter}</strong></>}
          </div>
        </div>

        {/* Leads table */}
        <div className="bg-white rounded-2xl border border-neutral-200/70 overflow-hidden">
          <div className="px-5 py-3 border-b border-neutral-200/70 flex items-center justify-between">
            <div className="text-[12.5px] font-semibold text-neutral-900">
              Seller leads <span className="text-neutral-500">· {leads.length}</span>
            </div>
            {stageFilter && (
              <button onClick={() => setStageFilter('')}
                      data-testid="admin-seller-os-clear-filter"
                      className="text-[11px] text-violet-700 hover:text-violet-900 font-semibold">
                Clear filter
              </button>
            )}
          </div>
          {loading ? (
            <div className="px-5 py-8 flex items-center gap-2 text-neutral-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>
          ) : leads.length === 0 ? (
            <div className="px-5 py-12 text-center text-[13px] text-neutral-500">
              No seller leads match this filter.
            </div>
          ) : (
            <table className="w-full text-[13px]">
              <thead className="bg-neutral-50 text-[10.5px] uppercase tracking-wider text-neutral-500 font-semibold">
                <tr>
                  <th className="text-left px-5 py-2.5">Business</th>
                  <th className="text-left px-3 py-2.5">Stage</th>
                  <th className="text-left px-3 py-2.5">Niche</th>
                  <th className="text-right px-3 py-2.5">Score</th>
                  <th className="text-left px-3 py-2.5">Email</th>
                  <th className="text-left px-5 py-2.5">User</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200/70">
                {leads.slice(0, 100).map((l) => (
                  <tr key={l.id} data-testid={`admin-seller-os-lead-${l.id}`} className="hover:bg-neutral-50">
                    <td className="px-5 py-2.5 font-medium text-neutral-900 truncate max-w-[240px]">
                      {l.business_name}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`inline-block text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full border ${STAGE_TONE[l.stage] || STAGE_TONE.discovered}`}>
                        {l.stage}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-neutral-600">{l.niche || '—'}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{l.seller_score != null ? Math.round(l.seller_score) : '—'}</td>
                    <td className="px-3 py-2.5 text-neutral-600 truncate max-w-[200px]">{l.email || <em className="text-neutral-400">none</em>}</td>
                    <td className="px-5 py-2.5 text-neutral-500 font-mono text-[11px]">{(l.user_id || '').slice(0, 12)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Retention workflows */}
        <div className="bg-white rounded-2xl border border-neutral-200/70 overflow-hidden">
          <div className="px-5 py-3 border-b border-neutral-200/70 flex items-center gap-2">
            <ShieldAlert size={14} className="text-violet-700" />
            <div className="text-[12.5px] font-semibold text-neutral-900">
              Retention workflows <span className="text-neutral-500">· {workflows.length}</span>
            </div>
          </div>
          {workflows.length === 0 ? (
            <div className="px-5 py-12 text-center text-[13px] text-neutral-500">No workflows running.</div>
          ) : (
            <div className="divide-y divide-neutral-200/70">
              {workflows.map((wf) => (
                <div key={wf.id} className="px-5 py-3" data-testid={`admin-seller-os-wf-${wf.id}`}>
                  <div className="flex items-center gap-3 mb-1.5">
                    <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full border ${
                      wf.status === 'complete'
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
                        : 'bg-violet-50 text-violet-700 border-violet-100'
                    }`}>{wf.status}</span>
                    <div className="text-[13px] font-semibold text-neutral-900">
                      Score <span className="tabular-nums">{Math.round(wf.score || 0)}</span>
                    </div>
                    <div className="text-[12px] text-neutral-600 flex-1 truncate">
                      {(wf.reasons || [])[0] || 'Multi-signal'}
                    </div>
                    <div className="text-[11px] text-neutral-500 font-mono">{(wf.user_id || '').slice(0, 10)}…</div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {(wf.steps || []).map((s) => (
                      <div key={s.step} title={`${s.step} · ${s.status}`}
                           className={`flex-1 h-1.5 rounded-full ${
                             s.status === 'ok' ? 'bg-emerald-500'
                             : s.status === 'failed' ? 'bg-rose-500'
                             : 'bg-neutral-200'
                           }`} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
};

export default AdminSellerOS;
