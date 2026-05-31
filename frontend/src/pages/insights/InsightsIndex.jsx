import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, ChevronLeft, ChevronRight, Calendar, Clock } from 'lucide-react';
import CVNavbar from '../../components/cv/CVNavbar';
import CVBackdrop from '../../components/cv/CVBackdrop';
import CVFooter from '../../components/cv/CVFooter';
import CVBreadcrumbs from '../../components/cv/CVBreadcrumbs';
import CVSeo, { ORG_SCHEMA, buildBreadcrumbSchema } from '../../components/cv/CVSeo';
import { POST_LIST, CATEGORIES, POSTS_PER_PAGE } from './posts';

const fmt = (iso) => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
    });
  } catch { return ''; }
};

const PostCard = ({ post, featured = false }) => {
  const m = post.__meta__ || {};
  return (
    <Link
      to={`/insights/${m.slug}`}
      data-testid={`insights-card-${m.slug}`}
      className={`group cv-glass rounded-2xl overflow-hidden hover:border-violet-400/40 transition-colors p-6 ${featured ? 'lg:p-10' : ''}`}
    >
      <div className="flex items-center gap-2 mb-4">
        <span className="text-[10.5px] uppercase tracking-[0.18em] font-semibold text-violet-300">
          {m.category_label || m.category}
        </span>
        <span className="w-1 h-1 rounded-full bg-zinc-700" />
        <span className="text-[11px] text-zinc-500 inline-flex items-center gap-1">
          <Clock size={10} /> {m.read_minutes || 5} min read
        </span>
      </div>
      <h3 className={`cv-display font-semibold text-white leading-tight group-hover:text-cyan-300 transition-colors ${featured ? 'text-3xl lg:text-4xl' : 'text-[19px]'}`}>
        {m.title}
      </h3>
      <p className={`mt-3 text-zinc-400 leading-relaxed ${featured ? 'text-[15px]' : 'text-[13.5px] line-clamp-3'}`}>
        {m.dek}
      </p>
      <div className="mt-5 flex items-center justify-between">
        <div className="flex items-center gap-2 text-[12px] text-zinc-500">
          <Calendar size={11} /> {fmt(m.published_at)}
          <span className="w-1 h-1 rounded-full bg-zinc-700" />
          <span className="text-zinc-400">{m.author?.name}</span>
        </div>
        <span className="inline-flex items-center gap-1 text-[12.5px] text-violet-300 font-semibold group-hover:gap-2 transition-all">
          Read <ArrowRight size={12} />
        </span>
      </div>
    </Link>
  );
};

const InsightsIndex = () => {
  const [category, setCategory] = useState('all');
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    if (category === 'all') return POST_LIST;
    return POST_LIST.filter((p) => p.__meta__?.category === category);
  }, [category]);

  const featured = filtered[0];
  const rest = filtered.slice(1);
  const totalPages = Math.max(1, Math.ceil(rest.length / POSTS_PER_PAGE));
  const pageStart = (page - 1) * POSTS_PER_PAGE;
  const paginated = rest.slice(pageStart, pageStart + POSTS_PER_PAGE);

  const breadcrumbs = [
    { label: 'Home', path: '/' },
    { label: 'Insights', path: '/insights' },
  ];

  return (
    <div className="min-h-screen cv-dark antialiased" data-testid="insights-index">
      <CVSeo
        title="Insights — Marketing OS Strategy, Playbooks & Automation"
        description="Long-form essays on AI marketing operating systems, seller acquisition, campaign planning, competitor intelligence, and multi-channel automation."
        path="/insights"
        schema={[ORG_SCHEMA, buildBreadcrumbSchema(breadcrumbs)]}
      />
      <CVNavbar />

      <section className="relative pt-32 pb-12 overflow-hidden">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <CVBreadcrumbs items={[{ label: 'Insights' }]} className="mb-5" />
          <span className="text-[11px] uppercase tracking-[0.22em] text-violet-300 font-semibold">CortexViral Insights</span>
          <h1 className="cv-display text-5xl sm:text-6xl font-semibold text-white mt-2 leading-[0.95]" data-testid="insights-h1">
            Operator essays on the <span className="cv-gradient-text">Marketing OS</span>.
          </h1>
          <p className="mt-6 max-w-2xl text-[16px] leading-relaxed text-zinc-400">
            Playbooks, frameworks, and concrete tactics from inside CortexViral. No fluff posts. No 'top 10' listicles. Just the operating manual we use ourselves.
          </p>
        </div>
      </section>

      {/* Category chips */}
      <section className="relative cv-dark pb-2">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-wrap gap-2" data-testid="insights-categories">
            {CATEGORIES.map((c) => (
              <button
                key={c.value}
                onClick={() => { setCategory(c.value); setPage(1); }}
                data-testid={`insights-category-${c.value}`}
                className={`text-[12.5px] font-semibold px-3.5 h-9 rounded-full transition-colors ${
                  category === c.value
                    ? 'bg-white text-zinc-950'
                    : 'cv-glass text-zinc-300 hover:text-white'
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Featured */}
      {featured && page === 1 && (
        <section className="relative cv-dark py-10" data-testid="insights-featured">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
            <PostCard post={featured} featured />
          </div>
        </section>
      )}

      {/* Grid */}
      <section className="relative cv-dark py-8">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="insights-grid">
            {paginated.map((p) => (
              <PostCard key={p.__meta__.slug} post={p} />
            ))}
          </div>
        </div>
      </section>

      {/* Pagination */}
      {totalPages > 1 && (
        <section className="relative cv-dark py-10" data-testid="insights-pagination">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="inline-flex items-center gap-1 px-3 h-9 rounded-full cv-glass text-[12.5px] text-zinc-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed"
              data-testid="insights-prev"
            >
              <ChevronLeft size={13} /> Newer
            </button>
            <div className="text-[12px] text-zinc-500">
              Page <span className="text-white font-semibold">{page}</span> of {totalPages}
            </div>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="inline-flex items-center gap-1 px-3 h-9 rounded-full cv-glass text-[12.5px] text-zinc-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed"
              data-testid="insights-next"
            >
              Older <ChevronRight size={13} />
            </button>
          </div>
        </section>
      )}

      <div className="h-12" />
      <CVFooter />
    </div>
  );
};

export default InsightsIndex;
