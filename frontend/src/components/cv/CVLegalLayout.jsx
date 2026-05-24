import React from 'react';

/**
 * Shared layout for legal pages (Privacy, Terms): two-column on desktop —
 * a sticky table-of-contents on the left, content on the right. Each
 * section in `sections` must declare { id, title, content (ReactNode) }.
 */
const CVLegalLayout = ({ intro, sections }) => (
  <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 grid lg:grid-cols-12 gap-10">
    {/* TOC */}
    <aside className="lg:col-span-3 order-2 lg:order-1">
      <nav
        aria-label="Section navigation"
        data-testid="cv-legal-toc"
        className="lg:sticky lg:top-28 cv-glass rounded-2xl p-5"
      >
        <div className="text-[10.5px] uppercase tracking-[0.22em] text-zinc-500 font-semibold mb-3">
          On this page
        </div>
        <ul className="space-y-1.5">
          {sections.map((s) => (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                className="block text-[12.5px] text-zinc-400 hover:text-cyan-300 leading-snug transition-colors"
                data-testid={`cv-legal-toc-link-${s.id}`}
              >
                {s.title}
              </a>
            </li>
          ))}
        </ul>
      </nav>
    </aside>

    {/* Content */}
    <div className="lg:col-span-9 order-1 lg:order-2">
      {intro && (
        <p className="text-[16px] text-zinc-300 leading-relaxed mb-10">{intro}</p>
      )}
      {sections.map((s) => (
        <section
          id={s.id}
          key={s.id}
          className="mb-10 scroll-mt-28"
          data-testid={`cv-legal-section-${s.id}`}
        >
          <h2 className="cv-display text-2xl font-semibold text-white mb-3">{s.title}</h2>
          <div className="text-[15px] text-zinc-400 leading-relaxed space-y-3 cv-prose">{s.content}</div>
        </section>
      ))}
    </div>
  </div>
);

export default CVLegalLayout;
