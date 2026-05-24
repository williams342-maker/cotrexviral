import React, { useState } from 'react';
import { Link, useParams, Navigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, ArrowLeft, Calendar, Clock } from 'lucide-react';
import CVNavbar from '../../components/cv/CVNavbar';
import CVBackdrop from '../../components/cv/CVBackdrop';
import CVFooter from '../../components/cv/CVFooter';
import CVSeo, { ORG_SCHEMA, buildArticleSchema } from '../../components/cv/CVSeo';
import { SelectAgentModal, AgentChatModal } from '../../components/Modals';
import { POSTS, getPost } from './posts';

const BlogShell = ({ children, seo }) => {
  const [selectOpen, setSelectOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);
  return (
    <div className="min-h-screen cv-dark antialiased">
      {seo}
      <CVNavbar onGetStarted={() => setSelectOpen(true)} />
      {children}
      <CVFooter />
      <SelectAgentModal open={selectOpen} onClose={() => setSelectOpen(false)} onSelect={(a) => { setActiveAgent(a); setSelectOpen(false); setTimeout(() => setChatOpen(true), 120); }} />
      <AgentChatModal open={chatOpen} onClose={() => setChatOpen(false)} agent={activeAgent} onBack={() => { setChatOpen(false); setSelectOpen(true); }} />
    </div>
  );
};

export const BlogIndex = () => {
  const [cluster, setCluster] = React.useState('all');
  const clusters = ['all', ...Array.from(new Set(POSTS.map((p) => p.cluster)))];
  const filtered = cluster === 'all' ? POSTS : POSTS.filter((p) => p.cluster === cluster);
  return (
  <BlogShell
    seo={
      <CVSeo
        title="CortexViral Blog — Viral Content & AI Marketing Insights"
        description="Deep guides on viral content, AI marketing tools, and social media growth. Learn what makes content go viral in 2026 — written by the CortexViral team."
        path="/blog"
        schema={ORG_SCHEMA}
      />
    }
  >
    <section className="relative pt-32 pb-12 overflow-hidden">
      <CVBackdrop variant="hero" />
      <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">CortexViral Blog</span>
        <h1 className="cv-display text-5xl sm:text-6xl font-semibold text-white mt-3 leading-[0.95]">
          Guides on <span className="cv-gradient-text">viral content</span> and AI marketing.
        </h1>
        <p className="mt-6 max-w-2xl mx-auto text-zinc-400 text-[16px]">Practical, no-fluff playbooks for creators, founders, and brands building compounding growth.</p>

        {/* Cluster filter */}
        <div className="mt-8 inline-flex flex-wrap items-center justify-center gap-2 cv-glass rounded-full p-1.5" data-testid="cv-blog-cluster-filter">
          {clusters.map((c) => (
            <button
              key={c}
              onClick={() => setCluster(c)}
              className={`px-3.5 h-9 rounded-full text-[12.5px] font-semibold transition-all capitalize ${
                cluster === c ? 'bg-white text-zinc-900' : 'text-zinc-400 hover:text-white'
              }`}
              data-testid={`cv-blog-cluster-${c.replace(/\s+/g, '-')}`}
            >
              {c === 'all' ? 'All' : c}
              <span className="ml-1.5 text-[10px] opacity-60">
                ({c === 'all' ? POSTS.length : POSTS.filter((p) => p.cluster === c).length})
              </span>
            </button>
          ))}
        </div>
      </div>
    </section>

    <section className="relative cv-dark pb-24">
      <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 grid md:grid-cols-2 gap-5">
        {filtered.map((p, i) => (
          <motion.div
            key={p.slug}
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: i * 0.04 }}
          >
            <Link to={`/blog/${p.slug}`} className="block cv-glass-strong rounded-3xl p-6 hover:border-violet-400/30 transition-colors group h-full">
              <span className="inline-block text-[10.5px] uppercase tracking-[0.2em] font-semibold px-2.5 py-1 rounded-full bg-violet-500/15 text-violet-300 border border-violet-500/25">{p.cluster}</span>
              <h2 className="cv-display text-2xl font-semibold text-white mt-4 group-hover:cv-gradient-text transition-colors">{p.title}</h2>
              <p className="mt-3 text-[14px] text-zinc-400 leading-relaxed">{p.excerpt}</p>
              <div className="mt-5 flex items-center gap-4 text-[11.5px] text-zinc-500">
                <span className="inline-flex items-center gap-1"><Calendar size={11} /> {new Date(p.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                <span className="inline-flex items-center gap-1"><Clock size={11} /> {p.readMin} min</span>
                <span className="ml-auto inline-flex items-center gap-1 text-cyan-300 font-semibold">Read <ArrowRight size={11} /></span>
              </div>
            </Link>
          </motion.div>
        ))}
      </div>
    </section>
  </BlogShell>
);
};

export const BlogPost = () => {
  const { slug } = useParams();
  const post = getPost(slug);
  if (!post) return <Navigate to="/blog" replace />;

  // Prefer posts from same cluster ("topical authority"). Fall back to others.
  const sameCluster = POSTS.filter((p) => p.slug !== post.slug && p.cluster === post.cluster).slice(0, 2);
  const otherPosts = sameCluster.length >= 2
    ? sameCluster
    : [...sameCluster, ...POSTS.filter((p) => p.slug !== post.slug && p.cluster !== post.cluster)].slice(0, 2);

  return (
    <BlogShell
      seo={
        <CVSeo
          title={`${post.title}`}
          description={post.description}
          path={`/blog/${post.slug}`}
          schema={buildArticleSchema({ title: post.title, description: post.description, slug: post.slug, date: post.date })}
        />
      }
    >
      <article className="relative pt-32 pb-12">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <Link to="/blog" className="inline-flex items-center gap-1.5 text-[13px] text-zinc-400 hover:text-white mb-6">
            <ArrowLeft size={13} /> All articles
          </Link>
          <span className="inline-block text-[10.5px] uppercase tracking-[0.2em] font-semibold px-2.5 py-1 rounded-full bg-violet-500/15 text-violet-300 border border-violet-500/25">{post.cluster}</span>
          <h1 className="cv-display text-4xl sm:text-5xl font-semibold text-white mt-5 leading-[1.05]">{post.title}</h1>
          <div className="mt-5 flex items-center gap-4 text-[12px] text-zinc-500">
            <span className="inline-flex items-center gap-1"><Calendar size={12} /> {new Date(post.date).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}</span>
            <span className="inline-flex items-center gap-1"><Clock size={12} /> {post.readMin} min read</span>
          </div>
          <p className="mt-6 text-[18px] text-zinc-300 leading-relaxed">{post.excerpt}</p>
        </div>
      </article>

      <section className="relative cv-dark pb-20">
        <div className="relative max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <div
            className="cv-prose text-[16px] text-zinc-300 leading-[1.75]"
            dangerouslySetInnerHTML={{ __html: post.body }}
          />
        </div>
      </section>

      <section className="relative cv-dark pb-24">
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="cv-display text-2xl font-semibold text-white mb-6">Keep reading</h2>
          <div className="grid md:grid-cols-2 gap-5">
            {otherPosts.map((p) => (
              <Link key={p.slug} to={`/blog/${p.slug}`} className="cv-glass rounded-2xl p-5 hover:border-cyan-400/30 transition-colors">
                <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-300">{p.cluster}</span>
                <h3 className="cv-display text-[18px] font-semibold text-white mt-3">{p.title}</h3>
                <p className="text-[13px] text-zinc-400 mt-2 line-clamp-2">{p.excerpt}</p>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </BlogShell>
  );
};
