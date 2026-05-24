import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, ArrowUp, ArrowDown, Plus } from 'lucide-react';

const RANGES = [
  { id: '24h', label: 'Last 24 hours' },
  { id: '48h', label: 'Last 48 hours' },
  { id: '7d', label: 'Last 7 days' },
  { id: '30d', label: 'Last 30 days' },
  { id: '60d', label: 'Last 60 days' },
  { id: '90d', label: 'Last 90 days' },
  { id: 'year', label: 'This year' },
  { id: 'lastyear', label: 'Last year' },
];

const Performance = () => {
  const [range, setRange] = useState('24h');
  const [overview, setOverview] = useState(null);
  const [sources, setSources] = useState([]);
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      axios.get(`${API}/performance/overview?range=${range}`, { withCredentials: true }),
      axios.get(`${API}/performance/sources?range=${range}`, { withCredentials: true }),
      axios.get(`${API}/performance/pages?range=${range}`, { withCredentials: true }),
    ]).then(([o, s, p]) => { setOverview(o.data); setSources(s.data); setPages(p.data); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [range]);

  return (
    <DashboardLayout title="Performance Analytics" subtitle="Track your marketing performance across sessions, revenue, sources and pages.">
      <div className="flex flex-wrap gap-2 mb-7">
        {RANGES.map((r) => (
          <button key={r.id} onClick={() => setRange(r.id)}
            className={`px-4 py-1.5 rounded-full text-[13px] font-medium border transition-all ${
              range === r.id
                ? 'bg-neutral-900 text-white border-neutral-900'
                : 'bg-white text-neutral-700 border-neutral-200 hover:border-neutral-300'
            }`}>
            {r.label}
          </button>
        ))}
        <button className="px-4 py-1.5 rounded-full text-[13px] font-medium border bg-white text-neutral-700 border-neutral-200 hover:border-neutral-300">Custom</button>
      </div>

      {loading || !overview ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : (
        <>
          <h2 className="text-[12px] uppercase tracking-wider text-neutral-500 font-semibold mb-3">Performance Metrics</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            {overview.metrics.map((m) => <MetricCard key={m.key} metric={m} />)}
            <button className="bg-white rounded-3xl p-6 border-2 border-dashed border-neutral-200 hover:border-neutral-300 hover:bg-neutral-50/50 transition-all flex flex-col items-center justify-center text-neutral-400 hover:text-neutral-600">
              <Plus size={24} className="mb-2" />
              <span className="text-[13px] font-medium">Add Metric</span>
            </button>
          </div>

          <div className="bg-white rounded-3xl p-6 border border-neutral-200/70 mb-8">
            <Chart series={overview.series} labels={overview.labels} />
            <div className="flex items-center justify-center gap-6 mt-4">
              {overview.series.map((s) => (
                <div key={s.key} className="flex items-center gap-2 text-[12.5px] text-neutral-600">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: s.color }} />
                  {s.label}
                </div>
              ))}
            </div>
          </div>

          <div className="grid lg:grid-cols-2 gap-5">
            <DataTable title="Session Source / Medium" columns={['Source', 'Now', 'Prev', '% Change']} rows={sources} render={(r, i) => (
              <tr key={i} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50/40">
                <td className="p-3 pl-5"><div className="flex items-center gap-2.5"><span className="w-5 h-5 rounded-full bg-neutral-100 text-neutral-500 text-[10px] font-semibold inline-flex items-center justify-center">{i + 1}</span><span className="text-[13.5px]">{r.source}</span></div></td>
                <td className="p-3 text-right text-[13.5px]">{r.now}</td>
                <td className="p-3 text-right text-[13.5px] text-neutral-500">{r.prev}</td>
                <td className="p-3 pr-5 text-right"><ChangeBadge value={r.change_pct} /></td>
              </tr>
            )} />

            <DataTable title="Top Landing Pages" columns={['Page', 'Now', 'Prev', '% Change']} rows={pages} render={(r, i) => (
              <tr key={i} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50/40">
                <td className="p-3 pl-5"><div className="flex items-center gap-2.5"><span className="w-5 h-5 rounded-full bg-neutral-100 text-neutral-500 text-[10px] font-semibold inline-flex items-center justify-center">{i + 1}</span><span className="text-[13.5px] font-mono">{r.page}</span></div></td>
                <td className="p-3 text-right text-[13.5px]">{r.now}</td>
                <td className="p-3 text-right text-[13.5px] text-neutral-500">{r.prev}</td>
                <td className="p-3 pr-5 text-right"><ChangeBadge value={r.change_pct} /></td>
              </tr>
            )} />
          </div>
        </>
      )}
    </DashboardLayout>
  );
};

const MetricCard = ({ metric }) => {
  const up = metric.change_pct >= 0;
  return (
    <div className="bg-white rounded-3xl p-6 border border-neutral-200/70">
      <div className="text-[11px] uppercase tracking-wider font-semibold text-[#1B7BFF] mb-3">{metric.label}</div>
      <div className="text-4xl font-medium tracking-tight">{metric.value}</div>
      <div className={`mt-2 inline-flex items-center gap-1 text-[13px] font-medium ${up ? 'text-emerald-600' : 'text-rose-600'}`}>
        {up ? <ArrowUp size={13} /> : <ArrowDown size={13} />}
        {Math.abs(metric.change_pct)}%
      </div>
    </div>
  );
};

const ChangeBadge = ({ value }) => {
  const up = value >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[12.5px] font-medium ${up ? 'text-emerald-600' : 'text-rose-600'}`}>
      {up ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
      {Math.abs(value)}%
    </span>
  );
};

const DataTable = ({ title, columns, rows, render }) => (
  <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-hidden">
    <div className="px-5 py-4 border-b border-neutral-200/70">
      <h3 className="text-[14.5px] font-semibold">{title}</h3>
    </div>
    <table className="w-full">
      <thead className="bg-neutral-50/40">
        <tr className="text-[11px] uppercase tracking-wider text-neutral-500 font-medium">
          <th className="p-3 pl-5 text-left">{columns[0]}</th>
          <th className="p-3 text-right">{columns[1]}</th>
          <th className="p-3 text-right">{columns[2]}</th>
          <th className="p-3 pr-5 text-right">{columns[3]}</th>
        </tr>
      </thead>
      <tbody>{rows.map(render)}</tbody>
    </table>
  </div>
);

const Chart = ({ series, labels }) => {
  const w = 900;
  const h = 260;
  const pad = { l: 40, r: 20, t: 20, b: 30 };
  const innerW = w - pad.l - pad.r;
  const innerH = h - pad.t - pad.b;
  const allValues = series.flatMap((s) => s.data);
  const maxV = Math.max(1, ...allValues);
  const xs = labels.length > 1 ? labels.map((_, i) => pad.l + (i / (labels.length - 1)) * innerW) : [pad.l + innerW / 2];

  const buildPath = (data) => {
    if (!data?.length) return '';
    return data.map((v, i) => {
      const y = pad.t + innerH - (v / maxV) * innerH;
      return `${i === 0 ? 'M' : 'L'}${xs[i]},${y}`;
    }).join(' ');
  };

  const buildArea = (data) => {
    if (!data?.length) return '';
    const line = buildPath(data);
    const last = pad.t + innerH;
    return `${line} L${xs[xs.length - 1]},${last} L${xs[0]},${last} Z`;
  };

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" preserveAspectRatio="none">
      {/* horizontal grid */}
      {[0, 0.25, 0.5, 0.75, 1].map((p, i) => (
        <line key={i} x1={pad.l} x2={pad.l + innerW} y1={pad.t + innerH * p} y2={pad.t + innerH * p}
          stroke="#f1f1ef" strokeWidth="1" />
      ))}
      {/* x labels */}
      {labels.filter((_, i) => i % Math.max(1, Math.floor(labels.length / 8)) === 0).map((l, i, arr) => {
        const idx = labels.indexOf(l);
        return <text key={i} x={xs[idx]} y={h - 8} fontSize="10" fill="#9ca3af" textAnchor="middle">{l}</text>;
      })}
      {/* areas + lines */}
      {series.map((s, i) => (
        <g key={s.key}>
          <path d={buildArea(s.data)} fill={s.color} opacity={0.08} />
          <path d={buildPath(s.data)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        </g>
      ))}
    </svg>
  );
};

export default Performance;
