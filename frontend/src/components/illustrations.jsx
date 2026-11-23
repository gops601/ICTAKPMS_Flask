/**
 * Hand-built SVG illustrations (no external assets, crisp at any size, theme-coloured).
 * To use your own photography/AI artwork instead, set VITE_HERO_IMAGE (see README) – the sign-in page picks it up.
 */

export function LogoMark({ size = 36, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" className={className} role="img" aria-label="ICTAKPMS logo">
      <defs>
        <linearGradient id="lm-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#10b981" /><stop offset="1" stopColor="#d97706" /></linearGradient>
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
        <linearGradient id="hi-blob" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#34d399" stopOpacity=".55" /><stop offset="1" stopColor="#fbbf24" stopOpacity=".35" /></linearGradient>
        <linearGradient id="hi-bar1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#34d399" /><stop offset="1" stopColor="#059669" /></linearGradient>
        <linearGradient id="hi-bar2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fcd34d" /><stop offset="1" stopColor="#d97706" /></linearGradient>
        <filter id="hi-shadow" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="14" stdDeviation="14" floodColor="#02120e" floodOpacity=".28" /></filter>
      </defs>
      <circle cx="270" cy="200" r="168" fill="url(#hi-blob)" />
      <circle cx="450" cy="70" r="46" fill="#fff" opacity=".06" /><circle cx="60" cy="330" r="34" fill="#fff" opacity=".07" />
      {[[70, 80], [470, 190], [110, 215], [420, 345]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="3" fill="#fff" opacity=".55" />)}

      {/* main window */}
      <g filter="url(#hi-shadow)">
        <rect x="70" y="62" width="330" height="236" rx="20" fill="#fff" />
        <path d="M70 82a20 20 0 0 1 20-20h290a20 20 0 0 1 20 20v14H70z" fill="#ecfdf5" />
        <circle cx="92" cy="79" r="5" fill="#fb7185" /><circle cx="110" cy="79" r="5" fill="#fbbf24" /><circle cx="128" cy="79" r="5" fill="#34d399" />
        <rect x="150" y="73" width="120" height="12" rx="6" fill="#d1fae5" />
        {/* side nav */}
        <rect x="84" y="108" width="56" height="176" rx="12" fill="#0f3d33" />
        {[124, 150, 176, 202].map((y, i) => <rect key={y} x="94" y={y} width="36" height="10" rx="5" fill="#fff" opacity={i === 0 ? 0.95 : 0.35} />)}
        {/* stat tiles */}
        {[[154, '#d1fae5', '#059669'], [231, '#fef3c7', '#d97706'], [308, '#fef3c7', '#d97706']].map(([x, bg, fg]) => (
          <g key={x}><rect x={x} y="108" width="68" height="42" rx="10" fill={bg} /><rect x={x + 10} y="118" width="26" height="6" rx="3" fill={fg} opacity=".55" /><rect x={x + 10} y="130" width="40" height="10" rx="4" fill={fg} /></g>
        ))}
        {/* bar chart */}
        <rect x="154" y="162" width="146" height="118" rx="12" fill="#f4faf7" />
        {[[168, 40, 'hi-bar1'], [190, 62, 'hi-bar2'], [212, 48, 'hi-bar1'], [234, 78, 'hi-bar2'], [256, 58, 'hi-bar1'], [278, 88, 'hi-bar2']].map(([x, h, g]) => (
          <rect key={x} x={x} y={268 - h} width="14" height={h} rx="5" fill={`url(#${g})`} />
        ))}
        {/* progress ring */}
        <rect x="310" y="162" width="76" height="118" rx="12" fill="#f4faf7" />
        <circle cx="348" cy="208" r="22" fill="none" stroke="#d1fae5" strokeWidth="8" />
        <circle cx="348" cy="208" r="22" fill="none" stroke="#d97706" strokeWidth="8" strokeLinecap="round" strokeDasharray="104 138" transform="rotate(-90 348 208)" />
        <rect x="334" y="204" width="28" height="8" rx="4" fill="#0f3d33" opacity=".8" />
        <rect x="322" y="246" width="52" height="6" rx="3" fill="#a7f3d0" /><rect x="328" y="258" width="40" height="6" rx="3" fill="#a7f3d0" />
      </g>

      {/* scrum card */}
      <g filter="url(#hi-shadow)">
        <rect x="330" y="236" width="150" height="112" rx="16" fill="#fff" />
        <rect x="344" y="250" width="40" height="8" rx="4" fill="#94a3b8" />
        {[[344, '#d1fae5', '#059669'], [392, '#fef3c7', '#d97706'], [440, '#fef3c7', '#d97706']].map(([x, bg, fg], c) => (
          <g key={x}>
            <rect x={x} y="266" width="34" height="68" rx="8" fill="#f1f5f9" />
            <rect x={x + 4} y="272" width="26" height="14" rx="4" fill={bg} /><rect x={x + 7} y="277" width="14" height="4" rx="2" fill={fg} />
            {c < 2 && <><rect x={x + 4} y="290" width="26" height="14" rx="4" fill={bg} /><rect x={x + 7} y="295" width="10" height="4" rx="2" fill={fg} /></>}
            {c === 0 && <rect x={x + 4} y="308" width="26" height="14" rx="4" fill="#d1fae5" />}
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
      <g filter="url(#hi-shadow)"><rect x="84" y="318" width="96" height="30" rx="15" fill="#fff" /><circle cx="102" cy="333" r="6" fill="#059669" /><rect x="114" y="327" width="52" height="5" rx="2.5" fill="#a7f3d0" /><rect x="114" y="335" width="34" height="5" rx="2.5" fill="#d1fae5" /></g>
    </svg>
  )
}

/** Friendly empty-state art (clipboard with a check). */
export function EmptyIllustration({ className = '', size = 112 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" className={className} role="img" aria-label="Nothing here yet">
      <defs><linearGradient id="ei-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#a7f3d0" /><stop offset="1" stopColor="#fde68a" /></linearGradient></defs>
      <circle cx="60" cy="62" r="46" fill="url(#ei-g)" opacity=".55" />
      <rect x="34" y="26" width="52" height="68" rx="9" fill="#fff" stroke="#a7f3d0" strokeWidth="2.5" />
      <rect x="47" y="19" width="26" height="14" rx="6" fill="#10b981" />
      {[48, 60, 72].map((y) => <g key={y}><circle cx="45" cy={y} r="3.2" fill="#d97706" /><rect x="53" y={y - 2.5} width="25" height="5" rx="2.5" fill="#d1fae5" /></g>)}
      <circle cx="92" cy="86" r="12" fill="#10b981" /><path d="m86 86 4 4 8-8.5" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Decorative art for the dashboard welcome banner: a small neural network with a rising trend line. */
export function BannerArt({ className = '' }) {
  const pts = [[40, 30], [40, 70], [40, 100], [100, 20], [100, 60], [100, 95], [160, 40], [160, 85], [220, 62]]
  const edges = [[0, 3], [0, 4], [1, 4], [1, 5], [2, 5], [2, 4], [3, 6], [4, 6], [4, 7], [5, 7], [6, 8], [7, 8]]
  return (
    <svg viewBox="0 0 260 120" className={className} aria-hidden="true">
      <circle cx="210" cy="26" r="38" fill="#fff" opacity=".07" />
      {edges.map(([a, b], i) => <line key={i} x1={pts[a][0]} y1={pts[a][1]} x2={pts[b][0]} y2={pts[b][1]} stroke="#fff" strokeOpacity=".3" strokeWidth="1.2" className="ai-link" />)}
      {pts.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i === 8 ? 8 : 4.5} fill={i === 8 ? '#fcd34d' : '#fff'} opacity={i === 8 ? 1 : 0.75} className="ai-node" style={{ animationDelay: `${i * 0.3}s` }} />)}
      <path d="M232 30l3 7 7 3-7 3-3 7-3-7-7-3 7-3z" fill="#fcd34d" />
    </svg>
  )
}

export function EmptyState({ title, children, className = '' }) {
  return (
    <div className={`flex flex-col items-center px-4 py-10 text-center ${className}`}>
      <div className="relative"><EmptyIllustration /><AiSpark size={34} className="absolute -right-3 -top-1" /></div>
      <p className="mt-2 text-sm font-medium text-slate-700">{title}</p>
      {children && <p className="mt-1 max-w-sm text-sm text-slate-500">{children}</p>}
    </div>
  )
}

/** Sign-in hero: an AI neural network feeding a central "AI" core, with floating insight cards. Animated, theme-coloured. */
export function AiNetworkHero({ className = '' }) {
  const layers = [
    [[60, 120], [60, 200], [60, 280]],
    [[150, 80], [150, 160], [150, 240], [150, 320]],
    [[240, 110], [240, 190], [240, 270]],
  ]
  const core = [345, 200]
  const out = [[450, 140], [450, 260]]
  const links = []
  layers.forEach((layer, li) => {
    const next = layers[li + 1]
    if (next) layer.forEach((a) => next.forEach((b) => links.push([a, b])))
  })
  layers[2].forEach((a) => links.push([a, core]))
  out.forEach((b) => links.push([core, b]))
  const nodes = [...layers.flat(), ...out]
  return (
    <svg viewBox="0 0 520 400" className={className} role="img" aria-label="Illustration of an AI neural network connected to a central AI core with project insights">
      <defs>
        <radialGradient id="an-glow" cx="50%" cy="50%" r="50%"><stop offset="0" stopColor="#34d399" stopOpacity=".55" /><stop offset="1" stopColor="#34d399" stopOpacity="0" /></radialGradient>
        <linearGradient id="an-core" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#10b981" /><stop offset="1" stopColor="#d97706" /></linearGradient>
        <filter id="an-shadow" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="12" stdDeviation="12" floodColor="#02120e" floodOpacity=".35" /></filter>
      </defs>
      <circle cx="345" cy="200" r="150" fill="url(#an-glow)" />
      {links.map(([a, b], i) => <line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#6ee7b7" strokeOpacity=".4" strokeWidth="1.2" className="ai-link" style={{ animationDelay: `${(i % 7) * 0.3}s` }} />)}
      {nodes.map(([x, y], i) => (
        <g key={i} className="ai-node" style={{ animationDelay: `${(i % 6) * 0.45}s` }}>
          <circle cx={x} cy={y} r="11" fill="#34d399" opacity=".18" /><circle cx={x} cy={y} r="5.5" fill="#a7f3d0" />
        </g>
      ))}
      {/* AI core chip */}
      <g filter="url(#an-shadow)">
        {[-24, -8, 8, 24].map((o) => <g key={o} stroke="#fcd34d" strokeWidth="3" strokeLinecap="round"><line x1={345 + o} y1="158" x2={345 + o} y2="148" /><line x1={345 + o} y1="242" x2={345 + o} y2="252" /><line x1="303" y1={200 + o} x2="293" y2={200 + o} /><line x1="387" y1={200 + o} x2="397" y2={200 + o} /></g>)}
        <rect x="303" y="158" width="84" height="84" rx="18" fill="url(#an-core)" />
        <rect x="313" y="168" width="64" height="64" rx="12" fill="#04201a" opacity=".35" />
        <text x="345" y="214" textAnchor="middle" fontFamily="Inter, system-ui, sans-serif" fontSize="30" fontWeight="700" fill="#fff">AI</text>
      </g>
      {/* floating insight cards */}
      <g className="ai-float" filter="url(#an-shadow)">
        <rect x="360" y="38" width="132" height="62" rx="14" fill="#fff" />
        <rect x="374" y="52" width="46" height="7" rx="3.5" fill="#6ee7b7" />
        {[0, 1, 2, 3, 4].map((i) => <rect key={i} x={376 + i * 16} y={90 - [12, 20, 15, 26, 22][i]} width="9" height={[12, 20, 15, 26, 22][i]} rx="3" fill={i % 2 ? '#d97706' : '#059669'} />)}
      </g>
      <g className="ai-float" style={{ animationDelay: '1.5s' }} filter="url(#an-shadow)">
        <rect x="372" y="300" width="132" height="54" rx="14" fill="#fff" />
        <circle cx="394" cy="327" r="11" fill="#10b981" /><path d="m388.500 327 4 4 7-8" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="412" y="318" width="64" height="6" rx="3" fill="#a7f3d0" /><rect x="412" y="331" width="44" height="6" rx="3" fill="#d1fae5" />
      </g>
      <g className="ai-float" style={{ animationDelay: '3s' }} filter="url(#an-shadow)">
        <rect x="14" y="326" width="104" height="44" rx="12" fill="#fff" />
        <path d="m34 340-8 8 8 8M52 340l8 8-8 8" fill="none" stroke="#059669" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="68" y="342" width="38" height="6" rx="3" fill="#fcd34d" /><rect x="68" y="353" width="26" height="6" rx="3" fill="#d1fae5" />
      </g>
    </svg>
  )
}

/** Small AI motif (node cluster + sparkle) used on empty states and cards. */
export function AiSpark({ size = 56, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className} aria-hidden="true">
      <g stroke="#10b981" strokeWidth="1.6" strokeOpacity=".6"><line x1="12" y1="46" x2="30" y2="30" /><line x1="30" y1="30" x2="50" y2="40" /><line x1="30" y1="30" x2="38" y2="12" /></g>
      {[[12, 46], [50, 40], [38, 12]].map(([x, y]) => <circle key={x} cx={x} cy={y} r="4.5" fill="#a7f3d0" stroke="#10b981" strokeWidth="1.5" />)}
      <path d="M30 18c1 7 5 11 12 12-7 1-11 5-12 12-1-7-5-11-12-12 7-1 11-5 12-12z" fill="#d97706" />
    </svg>
  )
}
