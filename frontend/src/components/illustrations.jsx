/**
 * Hand-built SVG illustrations (no external assets, crisp at any size, theme-coloured).
 * To use your own photography/AI artwork instead, set VITE_HERO_IMAGE (see README) – the sign-in page picks it up.
 */

export function LogoMark({ size = 36, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" className={className} role="img" aria-label="ICTAKPMS logo">
      <defs>
        <linearGradient id="lm-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#6d5bf0" /><stop offset="1" stopColor="#0d9488" /></linearGradient>
      </defs>
      <rect width="48" height="48" rx="13" fill="url(#lm-bg)" />
      <path d="M24 11 8.5 19l15.5 8 12-6.2V30h2.5V19.6z" fill="#fff" opacity=".95" />
      <path d="M15 25.2v5.1c0 2.3 4.1 4.2 9 4.2s9-1.9 9-4.2v-5.1l-9 4.6z" fill="#fff" opacity=".85" />
      <circle cx="37.2" cy="33" r="2" fill="#fcd34d" />
    </svg>
  )
}

/** Sign-in hero: a project dashboard, a Scrum card and success badges floating over soft shapes. */
export function HeroIllustration({ className = '' }) {
  return (
    <svg viewBox="0 0 520 400" className={className} role="img" aria-label="Illustration of a project dashboard with charts, a Scrum board and completed milestones">
      <defs>
        <linearGradient id="hi-blob" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#818cf8" stopOpacity=".55" /><stop offset="1" stopColor="#2dd4bf" stopOpacity=".35" /></linearGradient>
        <linearGradient id="hi-bar1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#818cf8" /><stop offset="1" stopColor="#4f46e5" /></linearGradient>
        <linearGradient id="hi-bar2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#5eead4" /><stop offset="1" stopColor="#0d9488" /></linearGradient>
        <filter id="hi-shadow" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="14" stdDeviation="14" floodColor="#0b0a2a" floodOpacity=".28" /></filter>
      </defs>
      <circle cx="270" cy="200" r="168" fill="url(#hi-blob)" />
      <circle cx="450" cy="70" r="46" fill="#fff" opacity=".06" /><circle cx="60" cy="330" r="34" fill="#fff" opacity=".07" />
      {[[70, 80], [470, 190], [110, 215], [420, 345]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="3" fill="#fff" opacity=".55" />)}

      {/* main window */}
      <g filter="url(#hi-shadow)">
        <rect x="70" y="62" width="330" height="236" rx="20" fill="#fff" />
        <path d="M70 82a20 20 0 0 1 20-20h290a20 20 0 0 1 20 20v14H70z" fill="#eef2ff" />
        <circle cx="92" cy="79" r="5" fill="#fb7185" /><circle cx="110" cy="79" r="5" fill="#fbbf24" /><circle cx="128" cy="79" r="5" fill="#34d399" />
        <rect x="150" y="73" width="120" height="12" rx="6" fill="#dbe0ff" />
        {/* side nav */}
        <rect x="84" y="108" width="56" height="176" rx="12" fill="#312e81" />
        {[124, 150, 176, 202].map((y, i) => <rect key={y} x="94" y={y} width="36" height="10" rx="5" fill="#fff" opacity={i === 0 ? 0.95 : 0.35} />)}
        {/* stat tiles */}
        {[[154, '#e0e7ff', '#4f46e5'], [231, '#ccfbf1', '#0d9488'], [308, '#fef3c7', '#d97706']].map(([x, bg, fg]) => (
          <g key={x}><rect x={x} y="108" width="68" height="42" rx="10" fill={bg} /><rect x={x + 10} y="118" width="26" height="6" rx="3" fill={fg} opacity=".55" /><rect x={x + 10} y="130" width="40" height="10" rx="4" fill={fg} /></g>
        ))}
        {/* bar chart */}
        <rect x="154" y="162" width="146" height="118" rx="12" fill="#f8f9ff" />
        {[[168, 40, 'hi-bar1'], [190, 62, 'hi-bar2'], [212, 48, 'hi-bar1'], [234, 78, 'hi-bar2'], [256, 58, 'hi-bar1'], [278, 88, 'hi-bar2']].map(([x, h, g]) => (
          <rect key={x} x={x} y={268 - h} width="14" height={h} rx="5" fill={`url(#${g})`} />
        ))}
        {/* progress ring */}
        <rect x="310" y="162" width="76" height="118" rx="12" fill="#f8f9ff" />
        <circle cx="348" cy="208" r="22" fill="none" stroke="#e0e7ff" strokeWidth="8" />
        <circle cx="348" cy="208" r="22" fill="none" stroke="#0d9488" strokeWidth="8" strokeLinecap="round" strokeDasharray="104 138" transform="rotate(-90 348 208)" />
        <rect x="334" y="204" width="28" height="8" rx="4" fill="#312e81" opacity=".8" />
        <rect x="322" y="246" width="52" height="6" rx="3" fill="#c7d2fe" /><rect x="328" y="258" width="40" height="6" rx="3" fill="#c7d2fe" />
      </g>

      {/* scrum card */}
      <g filter="url(#hi-shadow)">
        <rect x="330" y="236" width="150" height="112" rx="16" fill="#fff" />
        <rect x="344" y="250" width="40" height="8" rx="4" fill="#94a3b8" />
        {[[344, '#e0e7ff', '#4f46e5'], [392, '#fef3c7', '#d97706'], [440, '#ccfbf1', '#0d9488']].map(([x, bg, fg], c) => (
          <g key={x}>
            <rect x={x} y="266" width="34" height="68" rx="8" fill="#f1f5f9" />
            <rect x={x + 4} y="272" width="26" height="14" rx="4" fill={bg} /><rect x={x + 7} y="277" width="14" height="4" rx="2" fill={fg} />
            {c < 2 && <><rect x={x + 4} y="290" width="26" height="14" rx="4" fill={bg} /><rect x={x + 7} y="295" width="10" height="4" rx="2" fill={fg} /></>}
            {c === 0 && <rect x={x + 4} y="308" width="26" height="14" rx="4" fill="#e0e7ff" />}
          </g>
        ))}
      </g>

      {/* graduation cap */}
      <g transform="translate(404 18) rotate(10 40 30)" filter="url(#hi-shadow)">
        <path d="M40 4 4 22l36 18 36-18z" fill="#fcd34d" /><path d="M18 33v14c0 5 10 9 22 9s22-4 22-9V33L40 43z" fill="#f59e0b" />
        <path d="M72 24v22" stroke="#fcd34d" strokeWidth="3" strokeLinecap="round" /><circle cx="72" cy="50" r="4" fill="#fcd34d" />
      </g>

      {/* success badge */}
      <g filter="url(#hi-shadow)"><circle cx="72" cy="300" r="26" fill="#10b981" /><path d="m59 300 9 9 17-18" fill="none" stroke="#fff" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" /></g>
      <g filter="url(#hi-shadow)"><rect x="84" y="318" width="96" height="30" rx="15" fill="#fff" /><circle cx="102" cy="333" r="6" fill="#4f46e5" /><rect x="114" y="327" width="52" height="5" rx="2.5" fill="#c7d2fe" /><rect x="114" y="335" width="34" height="5" rx="2.5" fill="#e0e7ff" /></g>
    </svg>
  )
}

/** Friendly empty-state art (clipboard with a check). */
export function EmptyIllustration({ className = '', size = 112 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" className={className} role="img" aria-label="Nothing here yet">
      <defs><linearGradient id="ei-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#c7d2fe" /><stop offset="1" stopColor="#99f6e4" /></linearGradient></defs>
      <circle cx="60" cy="62" r="46" fill="url(#ei-g)" opacity=".55" />
      <rect x="34" y="26" width="52" height="68" rx="9" fill="#fff" stroke="#c7d2fe" strokeWidth="2.5" />
      <rect x="47" y="19" width="26" height="14" rx="6" fill="#6366f1" />
      {[48, 60, 72].map((y) => <g key={y}><circle cx="45" cy={y} r="3.2" fill="#14b8a6" /><rect x="53" y={y - 2.5} width="25" height="5" rx="2.5" fill="#dbe0ff" /></g>)}
      <circle cx="92" cy="86" r="12" fill="#10b981" /><path d="m86 86 4 4 8-8.5" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Decorative art for the dashboard welcome banner (rising bars, a target and floating dots). */
export function BannerArt({ className = '' }) {
  return (
    <svg viewBox="0 0 260 120" className={className} aria-hidden="true">
      <circle cx="210" cy="26" r="38" fill="#fff" opacity=".08" /><circle cx="52" cy="104" r="30" fill="#fff" opacity=".07" />
      {[[40, 34], [68, 52], [96, 40], [124, 70], [152, 58], [180, 86]].map(([x, h]) => <rect key={x} x={x} y={108 - h} width="16" height={h} rx="6" fill="#fff" opacity={0.28 + h / 200} />)}
      <path d="M36 70c28-4 40-26 70-22s38 22 70 6 44-34 66-30" fill="none" stroke="#fcd34d" strokeWidth="4" strokeLinecap="round" />
      <circle cx="242" cy="26" r="7" fill="#fcd34d" /><circle cx="242" cy="26" r="3" fill="#fff" />
    </svg>
  )
}

export function EmptyState({ title, children, className = '' }) {
  return (
    <div className={`flex flex-col items-center px-4 py-10 text-center ${className}`}>
      <EmptyIllustration />
      <p className="mt-2 text-sm font-medium text-slate-700">{title}</p>
      {children && <p className="mt-1 max-w-sm text-sm text-slate-500">{children}</p>}
    </div>
  )
}
