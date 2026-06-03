import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { motion } from 'framer-motion';
import { Activity, Zap } from 'lucide-react';
import { API } from '../../../context/AuthContext';
import CortexThinkingCard from './CortexThinkingCard';
import ActiveMissionRail   from './ActiveMissionRail';
import ActiveWorkRail      from './ActiveWorkRail';

/* CortexLivePanel — one glanceable "what is Cortex doing right now?"
   widget. Wraps the three live-progress surfaces (conversational
   analysis, missions, work jobs) with one consistent header, one
   activity count, and one pulse so users don't have to triangulate
   between three different rail components.

   Each inner rail still owns its own behaviour (polling, retry,
   cancel, completed-flash) — this component is purely a visual
   container. Auto-collapses to nothing when none of the three are
   active (zero visual cost on a quiet dashboard). */

const CortexLivePanel = ({
  thinkingTurn,
  missions = [], missionsLoading = false,
  onOpenMission, onMissionCancelled, onScrollToTurn, onLaunchScan,
}) => {
  // Lightweight poll of analysis-jobs JUST for the activity count
  // header — the actual job tiles are rendered by ActiveWorkRail which
  // does its own polling. We accept the small dupe so the header can
  // give an accurate "5 live" without prop-drilling refs everywhere.
  const [activeJobCount, setActiveJobCount] = useState(0);

  const refreshJobCount = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/analysis-jobs`,
                                  { withCredentials: true });
      const jobs = r.data?.jobs || [];
      // running OR queued counts as live; completed/failed don't.
      const live = jobs.filter((j) => j.status === 'running' || j.status === 'queued').length;
      setActiveJobCount(live);
    } catch (_e) { /* keep prior count */ }
  }, []);

  useEffect(() => {
    refreshJobCount();
    const id = setInterval(refreshJobCount, 3000);
    return () => clearInterval(id);
  }, [refreshJobCount]);

  const thinkingCount   = thinkingTurn ? 1 : 0;
  const runningMissions = (missions || []).filter(
    (m) => m.status === 'running' || m.status === 'active' || !m.status).length;
  const totalLive = thinkingCount + runningMissions + activeJobCount;

  // Nothing live? Render nothing. Avoids a permanent "Cortex Live: 0"
  // header from cluttering the rail.
  if (totalLive === 0) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      data-testid="cortex-live-panel"
      className="rounded-2xl border border-violet-500/25 bg-gradient-to-br
                 from-violet-500/[0.06] via-fuchsia-500/[0.02] to-transparent
                 backdrop-blur-sm p-3">
      <header className="flex items-center gap-2 mb-3 pb-2 border-b border-violet-500/15">
        <span className="w-5 h-5 rounded-md bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center shadow-sm shadow-violet-500/30">
          <Zap size={11} className="text-white" />
        </span>
        <span className="text-[10.5px] uppercase tracking-[0.18em] font-bold text-violet-200">
          Cortex Live
        </span>
        <span className="text-[10px] text-violet-300/70 ml-1">
          {totalLive} active
        </span>
        <span className="ml-auto flex items-center gap-1 text-[10px] text-emerald-300">
          <Activity size={10} className="animate-pulse" />
          working
        </span>
      </header>

      <div className="space-y-3" data-testid="cortex-live-sections">
        {/* 1. In-flight conversational analysis (indeterminate progress) */}
        {thinkingTurn && (
          <CortexThinkingCard turn={thinkingTurn}
                                onScrollToTurn={onScrollToTurn} />
        )}

        {/* 2. Active missions (determinate progress, ETA, current/target) */}
        {runningMissions > 0 && (
          <ActiveMissionRail missions={missions}
                                loading={missionsLoading}
                                onOpenDetails={onOpenMission}
                                onCancelled={onMissionCancelled} />
        )}

        {/* 3. Active analysis jobs (determinate %, retry/debug on failure) */}
        {activeJobCount > 0 && (
          <ActiveWorkRail onLaunchScan={onLaunchScan} />
        )}
      </div>
    </motion.section>
  );
};

export default CortexLivePanel;
