import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Sparkles } from 'lucide-react';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import AITaskRunner from '../../components/ai/AITaskRunner';
import AIRunHistory from '../../components/ai/AIRunHistory';
import AIRunDetail from '../../components/ai/AIRunDetail';

const AICommandCenter = () => {
  const [runs, setRuns] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/ai/runs?limit=50`, { withCredentials: true });
      const next = data.runs || [];
      setRuns(next);
      setSelected((current) => current || next[0] || null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadRuns(); }, [loadRuns]);

  const handleComplete = (run) => {
    setSelected(run);
    setRuns((current) => [run, ...current.filter((item) => item.run_id !== run.run_id)]);
  };

  return (
    <DashboardLayout
      title="AI Command Center"
      subtitle="Run structured AI tasks through one governed orchestration layer."
      headerExtra={(
        <div className="flex items-center gap-2 text-xs text-violet-200 border border-violet-400/20 bg-violet-400/10 rounded-full px-3 py-1.5">
          <Sparkles size={13} /> Central orchestration active
        </div>
      )}
    >
      <div className="space-y-6">
        <AITaskRunner onComplete={handleComplete} />
        <div className="grid lg:grid-cols-[310px_minmax(0,1fr)] gap-6 items-start">
          <AIRunHistory
            runs={runs}
            loading={loading}
            selectedId={selected?.run_id}
            onSelect={setSelected}
          />
          <AIRunDetail run={selected} />
        </div>
      </div>
    </DashboardLayout>
  );
};

export default AICommandCenter;
