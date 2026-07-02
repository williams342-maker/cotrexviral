import React from 'react';

const STYLES = {
  pending: 'border-amber-400/20 bg-amber-400/10 text-amber-200',
  approved: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-200',
  rejected: 'border-rose-400/20 bg-rose-400/10 text-rose-200',
  not_required: 'border-zinc-400/20 bg-zinc-400/10 text-zinc-300',
};

const ApprovalStatusBadge = ({ status = 'not_required' }) => (
  <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${STYLES[status] || STYLES.not_required}`}>
    {String(status).replace(/_/g, ' ')}
  </span>
);

export default ApprovalStatusBadge;

