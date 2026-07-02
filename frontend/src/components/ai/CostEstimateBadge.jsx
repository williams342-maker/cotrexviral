import React from 'react';

const CostEstimateBadge = ({ cost = 0 }) => (
  <span className="inline-flex items-center rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-[11px] font-semibold text-cyan-200">
    ${Number(cost || 0).toFixed(6)}
  </span>
);

export default CostEstimateBadge;

