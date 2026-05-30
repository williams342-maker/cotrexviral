import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, RefreshCw, Mail, Send, Inbox, AlertCircle } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

const STATUS_TONE = {
  sent:     'bg-emerald-50 text-emerald-700 border-emerald-100',
  rejected: 'bg-rose-50 text-rose-700 border-rose-100',
  skipped:  'bg-amber-50 text-amber-700 border-amber-100',
  error:    'bg-rose-50 text-rose-700 border-rose-100',
};

const PROVIDER_TONE = {
  sendgrid: 'bg-blue-50 text-blue-700 border-blue-100',
  mailtrap: 'bg-violet-50 text-violet-700 border-violet-100',
  mailgun:  'bg-amber-50 text-amber-700 border-amber-100',
};

const AdminEmailLog = () => {
  const { toast } = useToast();
  const [health, setHealth] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ tag: '', provider: '', status: '' });
  const [testTo, setTestTo] = useState('');
  const [testTpl, setTestTpl] = useState('welcome');
  const [testing, setTesting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ limit: '200' });
      Object.entries(filters).forEach(([k, v]) => v && qs.set(k, v));
      const [h, l] = await Promise.all([
        axios.get(`${API}/admin/email/health?hours=72`, { withCredentials: true }),
        axios.get(`${API}/admin/email/logs?${qs.toString()}`, { withCredentials: true }),
      ]);
      setHealth(h.data);
      setLogs(l.data?.logs || []);
    } catch {
      toast({ title: 'Load failed', variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [filters]);

  const runTestSend = async () => {
    if (!testTo) {
      toast({ title: 'Enter a recipient email', variant: 'destructive' });
      return;
    }
    setTesting(true);
    try {
      const r = await axios.post(`${API}/admin/email/test-send`,
        { to: testTo, template: testTpl },
        { withCredentials: true });
      toast({
        title: r.data.sent ? `✓ Sent via ${r.data.provider}` : 'Send failed',
        description: r.data.sent
          ? `id ${r.data.message_id || '—'} · template ${r.data.template}`
          : (r.data.error || r.data.skipped || 'No provider configured'),
        variant: r.data.sent ? 'default' : 'destructive',
      });
      load();
    } catch (e) {
      toast({ title: 'Test send failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setTesting(false); }
  };

  const total = health?.total || 0;
  const sent = health?.sent || 0;
  const rate = total > 0 ? Math.round((sent / total) * 1000) / 10 : null;

  return (
    <DashboardLayout
      title="Admin · Email Log"
      subtitle="Every transactional + lifecycle email delivered through the SendGrid → Mailtrap → Mailgun chain."
      headerExtra={
        <button onClick={load} disabled={loading}
                data-testid="admin-emaillog-refresh"
                className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-neutral-900 text-white hover:bg-neutral-700 transition flex items-center gap-1.5 disabled:opacity-50">
          {loading ? <Loader2 className="animate-spin" size={13} /> : <RefreshCw size={13} />}
          Refresh
        </button>
      }
    >
      <div className="space-y-6" data-testid="admin-emaillog-page">
        {/* Health top-line */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile icon={Mail}  label="Total (72h)" value={total} tone="bg-neutral-100 text-neutral-700" />
          <Tile icon={Send}  label="Sent"        value={sent}  tone="bg-emerald-50 text-emerald-700" />
          <Tile icon={Inbox} label="Delivery %"  value={rate != null ? `${rate}%` : '—'} tone="bg-blue-50 text-blue-700" />
          <Tile icon={AlertCircle} label="Skipped / rejected"
                value={(health?.skipped || 0) + (health?.rejected || 0)}
                tone="bg-amber-50 text-amber-700" />
        </div>

        {/* Per-provider + per-lifecycle */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Card title="By provider">
            {Object.keys(health?.by_provider || {}).length === 0 ? (
              <div className="text-[12px] text-neutral-500 italic">No deliveries yet.</div>
            ) : (
              Object.entries(health.by_provider).map(([p, n]) => (
                <div key={p} className="flex items-center justify-between text-[13px] py-1"
                     data-testid={`admin-emaillog-provider-${p}`}>
                  <span className={`inline-block text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full border ${PROVIDER_TONE[p] || 'bg-neutral-100 text-neutral-700 border-neutral-200'}`}>
                    {p}
                  </span>
                  <span className="tabular-nums font-medium">{n}</span>
                </div>
              ))
            )}
          </Card>
          <Card title="Seller-OS lifecycle">
            {Object.keys(health?.by_lifecycle || {}).length === 0 ? (
              <div className="text-[12px] text-neutral-500 italic">No lifecycle emails yet.</div>
            ) : (
              Object.entries(health.by_lifecycle).map(([t, n]) => (
                <div key={t} className="flex items-center justify-between text-[13px] py-1"
                     data-testid={`admin-emaillog-lifecycle-${t}`}>
                  <span className="text-neutral-700 capitalize">{t.replace('-', ' ')}</span>
                  <span className="tabular-nums font-medium">{n}</span>
                </div>
              ))
            )}
          </Card>
        </div>

        {/* SendGrid test-send */}
        <div className="bg-white rounded-2xl border border-neutral-200/70 p-5">
          <div className="text-[12px] uppercase tracking-wider text-neutral-500 font-semibold mb-3">
            SendGrid test-send
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input type="email" value={testTo} onChange={(e) => setTestTo(e.target.value)}
                   placeholder="you@yourdomain.com"
                   data-testid="admin-emaillog-test-to"
                   className="flex-1 min-w-[220px] px-3 py-2 rounded-lg border border-neutral-200 text-[13px]" />
            <select value={testTpl} onChange={(e) => setTestTpl(e.target.value)}
                    data-testid="admin-emaillog-test-template"
                    className="px-3 py-2 rounded-lg border border-neutral-200 text-[13px]">
              <option value="welcome">Welcome</option>
              <option value="audit">Audit (with HTML attachment)</option>
              <option value="nudge">Nudge</option>
              <option value="recovery">Churn recovery</option>
            </select>
            <button onClick={runTestSend} disabled={testing || !testTo}
                    data-testid="admin-emaillog-test-send"
                    className="text-[12px] font-semibold px-3.5 py-2 rounded-lg bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 transition flex items-center gap-1.5 disabled:opacity-50">
              {testing ? <Loader2 className="animate-spin" size={13} /> : <Send size={13} />}
              {testing ? 'Sending…' : 'Send test'}
            </button>
          </div>
          <div className="text-[11.5px] text-neutral-500 mt-2.5">
            Picks the first configured provider in the chain. If <code>SENDGRID_API_KEY</code> is set and the sender is verified, SendGrid delivers; otherwise it falls through to Mailtrap → Mailgun.
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-neutral-200/70 p-4 flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-wider text-neutral-500 font-semibold mr-2">Filter</span>
          <select value={filters.tag} onChange={(e) => setFilters({ ...filters, tag: e.target.value })}
                  data-testid="admin-emaillog-filter-tag"
                  className="px-3 py-1.5 rounded-md border border-neutral-200 text-[12.5px]">
            <option value="">Any tag</option>
            <option value="seller-lifecycle">seller-lifecycle</option>
            <option value="welcome">welcome</option>
            <option value="audit">audit</option>
            <option value="nudge">nudge</option>
            <option value="churn-recovery">churn-recovery</option>
          </select>
          <select value={filters.provider} onChange={(e) => setFilters({ ...filters, provider: e.target.value })}
                  data-testid="admin-emaillog-filter-provider"
                  className="px-3 py-1.5 rounded-md border border-neutral-200 text-[12.5px]">
            <option value="">Any provider</option>
            <option value="sendgrid">sendgrid</option>
            <option value="mailtrap">mailtrap</option>
            <option value="mailgun">mailgun</option>
          </select>
          <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                  data-testid="admin-emaillog-filter-status"
                  className="px-3 py-1.5 rounded-md border border-neutral-200 text-[12.5px]">
            <option value="">Any status</option>
            <option value="sent">sent</option>
            <option value="rejected">rejected</option>
            <option value="skipped">skipped</option>
            <option value="error">error</option>
          </select>
          {(filters.tag || filters.provider || filters.status) && (
            <button onClick={() => setFilters({ tag: '', provider: '', status: '' })}
                    data-testid="admin-emaillog-filter-clear"
                    className="text-[11.5px] text-violet-700 hover:text-violet-900 font-semibold ml-1">
              Clear
            </button>
          )}
        </div>

        {/* Logs table */}
        <div className="bg-white rounded-2xl border border-neutral-200/70 overflow-hidden">
          <div className="px-5 py-3 border-b border-neutral-200/70 text-[12.5px] font-semibold text-neutral-900">
            Newest deliveries <span className="text-neutral-500">· {logs.length}</span>
          </div>
          {loading ? (
            <div className="px-5 py-8 flex items-center gap-2 text-neutral-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>
          ) : logs.length === 0 ? (
            <div className="px-5 py-12 text-center text-[13px] text-neutral-500">No deliveries match this filter.</div>
          ) : (
            <table className="w-full text-[13px]">
              <thead className="bg-neutral-50 text-[10.5px] uppercase tracking-wider text-neutral-500 font-semibold">
                <tr>
                  <th className="text-left px-5 py-2.5">When</th>
                  <th className="text-left px-3 py-2.5">To</th>
                  <th className="text-left px-3 py-2.5">Subject</th>
                  <th className="text-left px-3 py-2.5">Tags</th>
                  <th className="text-left px-3 py-2.5">Provider</th>
                  <th className="text-left px-3 py-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200/70">
                {logs.map((row) => (
                  <tr key={row.id || `${row.to}-${row.created_at}`}
                      data-testid={`admin-emaillog-row-${row.id || row.created_at}`}
                      className="hover:bg-neutral-50">
                    <td className="px-5 py-2.5 text-neutral-500 whitespace-nowrap">{new Date(row.created_at).toLocaleString()}</td>
                    <td className="px-3 py-2.5 text-neutral-800 truncate max-w-[200px]">{row.to}</td>
                    <td className="px-3 py-2.5 text-neutral-900 font-medium truncate max-w-[320px]">{row.subject}</td>
                    <td className="px-3 py-2.5 text-neutral-600 text-[11.5px]">{(row.tags || []).join(', ') || '—'}</td>
                    <td className="px-3 py-2.5">
                      <span className={`inline-block text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full border ${PROVIDER_TONE[row.provider] || 'bg-neutral-100 text-neutral-700 border-neutral-200'}`}>
                        {row.provider || '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`inline-block text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full border ${STATUS_TONE[row.status] || 'bg-neutral-100 text-neutral-700 border-neutral-200'}`}>
                        {row.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
};

const Tile = ({ icon: Icon, label, value, tone }) => (
  <div className="bg-white rounded-2xl p-4 border border-neutral-200/70"
       data-testid={`admin-emaillog-tile-${label.toLowerCase().replace(/\s+/g, '-')}`}>
    <div className={`inline-flex items-center justify-center w-8 h-8 rounded-lg ${tone} mb-2`}>
      <Icon size={14} />
    </div>
    <div className="text-[10.5px] uppercase tracking-wider text-neutral-500 font-semibold">{label}</div>
    <div className="text-2xl tabular-nums font-medium text-neutral-900 mt-0.5">{value}</div>
  </div>
);

const Card = ({ title, children }) => (
  <div className="bg-white rounded-2xl border border-neutral-200/70 p-4">
    <div className="text-[11px] uppercase tracking-wider text-neutral-500 font-semibold mb-2">{title}</div>
    {children}
  </div>
);

export default AdminEmailLog;
