import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Home } from 'lucide-react';

/**
 * Visual breadcrumb trail. The JSON-LD BreadcrumbList schema is emitted
 * separately via buildBreadcrumbSchema() inside the page's <CVSeo />.
 *
 * Props:
 *   items: [{ label, to? }]  — last item is current page (no `to`).
 *   className?: extra wrapper classes
 */
const CVBreadcrumbs = ({ items = [], className = '' }) => {
  if (!items.length) return null;
  return (
    <nav
      aria-label="Breadcrumb"
      data-testid="cv-breadcrumbs"
      className={`flex items-center flex-wrap gap-1.5 text-[12px] text-zinc-500 ${className}`}
    >
      <Link
        to="/"
        className="inline-flex items-center gap-1 hover:text-zinc-300 transition-colors"
        data-testid="cv-breadcrumb-home"
      >
        <Home size={11} />
        <span className="sr-only">Home</span>
      </Link>
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={`${item.label}-${i}`} className="inline-flex items-center gap-1.5">
            <ChevronRight size={11} className="text-zinc-700" />
            {isLast || !item.to ? (
              <span
                aria-current={isLast ? 'page' : undefined}
                className="text-zinc-300"
                data-testid={`cv-breadcrumb-current`}
              >
                {item.label}
              </span>
            ) : (
              <Link
                to={item.to}
                className="hover:text-zinc-300 transition-colors"
                data-testid={`cv-breadcrumb-link-${i}`}
              >
                {item.label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
};

export default CVBreadcrumbs;
