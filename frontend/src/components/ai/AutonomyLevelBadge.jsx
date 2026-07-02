import React from 'react';

const LABELS = {
  0: 'L0 · Suggest',
  1: 'L1 · Draft',
  2: 'L2 · Approval',
  3: 'L3 · Approved execution',
  4: 'L4 · Rules-bounded',
  5: 'L5 · Autonomous',
};

const AutonomyLevelBadge = ({ level = 1 }) => (
  <span className="inline-flex items-center rounded-full border border-violet-400/20 bg-violet-400/10 px-2.5 py-1 text-[11px] font-semibold text-violet-200">
    {LABELS[level] || `L${level}`}
  </span>
);

export default AutonomyLevelBadge;

