import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2, Play, ShieldAlert } from 'lucide-react';
import { API } from '../../context/AuthContext';

const TASKS = [
  'campaign_plan', 'social_post', 'reddit_post', 'pinterest_pin',
  'seo_recommendation', 'listing_optimization', 'email_reply',
  'ad_script', 'daily_brief', 'autonomous_action_plan',
];

const AUTONOMY = [
  [0, 'L0 · Suggest only'],
  [1, 'L1 · Draft only'],
  [2, 'L2 · Prepare for approval'],
  [3, 'L3 · Explicit approval required'],
  [4, 'L4 · Rules-bounded (execution disabled)'],
  [5, 'L5 · Fully autonomous (disabled)'],
];

const AITaskRunner = ({ onComplete }) => {
  const [taskType, setTaskType] = useState('ad_script');
  const [goal, setGoal] = useState('');
  const [autonomy, setAutonomy] = useState(1);
  const [context, setContext] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    axios.get(`${API}/user/preferences`, { withCredentials: true })
      .then((r) => setAutonomy(Number(r.data?.preferences?.ai_autonomy_level ?? 1)))
      .catch(() => setAutonomy(1));
  }, []);

  const run = async (e) => {
    e.preventDefault();
    if (!goal.trim()) return;
    setLoading(true);
    setError('');
    try {
      let parsedContext = {};
      if (context.trim()) parsedContext = JSON.parse(context);
      const { data } = await axios.post(`${API}/ai/execute`, {
        task_type: taskType,
        user_goal: goal.trim(),
        autonomy_level: Number(autonomy),
        context: parsedContext,
      }, { withCredentials: true });
      onComplete?.(data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'AI run failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={run} className="rounded-2xl border border-white/10 bg-white/[0.035] p-5 space-y-4">
      <div className="grid md:grid-cols-2 gap-4">
        <label className="space-y-1.5">
          <span className="text-xs font-semibold text-zinc-300">Task type</span>
          <select
            value={taskType}
            onChange={(e) => setTaskType(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-zinc-950 px-3 h-11 text-sm text-zinc-100"
          >
            {TASKS.map((task) => <option key={task} value={task}>{task.replace(/_/g, ' ')}</option>)}
          </select>
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-semibold text-zinc-300">Autonomy level · defaults from Settings</span>
          <select
            value={autonomy}
            onChange={(e) => setAutonomy(Number(e.target.value))}
            className="w-full rounded-xl border border-white/10 bg-zinc-950 px-3 h-11 text-sm text-zinc-100"
          >
            {AUTONOMY.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
      </div>

      <label className="space-y-1.5 block">
        <span className="text-xs font-semibold text-zinc-300">Goal</span>
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          rows={4}
          placeholder="Describe the outcome you want the AI to prepare…"
          className="w-full rounded-xl border border-white/10 bg-zinc-950 px-3 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 resize-y"
        />
      </label>

      <label className="space-y-1.5 block">
        <span className="text-xs font-semibold text-zinc-300">Context JSON <span className="font-normal text-zinc-600">(optional)</span></span>
        <textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          rows={3}
          placeholder={'{"brand":"Crafters Market","tone":"practical"}'}
          className="w-full rounded-xl border border-white/10 bg-zinc-950 px-3 py-3 font-mono text-xs text-zinc-100 placeholder:text-zinc-700 resize-y"
        />
      </label>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-[11px] text-zinc-500">
          <ShieldAlert size={13} className="text-amber-300" />
          External posting, email, ads, and marketplace actions are disabled.
        </p>
        <button
          type="submit"
          disabled={loading || !goal.trim()}
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 px-5 h-11 text-sm font-semibold text-white disabled:opacity-50"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
          {loading ? 'Running…' : 'Run AI task'}
        </button>
      </div>
      {error && <div className="rounded-xl border border-rose-400/20 bg-rose-400/10 p-3 text-sm text-rose-200">{error}</div>}
    </form>
  );
};

export default AITaskRunner;

