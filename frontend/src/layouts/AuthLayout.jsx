import { CheckCircle2, ShieldCheck } from 'lucide-react'
import { AiNetworkHero, LogoMark } from '../components/illustrations'
import { APP_NAME, APP_TAGLINE } from '../utils/brand'

const FEATURES = ['SRS submission, review and approval', 'Scrum boards with weekly mentor evaluations', 'Live dashboards and batch-wise reports']

/** Two-panel sign-in shell. Set VITE_HERO_IMAGE to show your own photo/AI artwork instead of the built-in illustration. */
export default function AuthLayout({ title, subtitle, children }) {
  const heroImage = import.meta.env.VITE_HERO_IMAGE
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <aside className="hero-gradient relative hidden flex-col justify-between overflow-hidden p-12 text-white lg:flex">
        {/* soft decorative glows */}
        <div className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-emerald-400/10 blur-3xl" aria-hidden />
        <div className="pointer-events-none absolute -bottom-32 right-0 h-80 w-80 rounded-full bg-amber-400/10 blur-3xl" aria-hidden />
        <div className="relative flex items-center gap-3">
          <LogoMark size={44} />
          <div><div className="text-2xl font-bold tracking-tight">{APP_NAME}</div><div className="text-sm text-emerald-200">{APP_TAGLINE}</div></div>
        </div>
        <div className="relative">
          <p className="mb-3 inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-medium uppercase tracking-widest text-amber-300 ring-1 ring-white/15">AI-era project learning</p>
          <h2 className="max-w-md text-3xl font-semibold leading-tight">From problem statement to final evaluation, in one place.</h2>
          {heroImage
            ? <img src={heroImage} alt="" className="mt-6 max-h-[340px] w-full rounded-2xl object-cover shadow-2xl" />
            : <AiNetworkHero className="mt-4 w-full max-w-xl" />}
        </div>
        <ul className="relative space-y-2 text-sm text-emerald-50/90">
          {FEATURES.map((f) => <li key={f} className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-amber-300" aria-hidden />{f}</li>)}
        </ul>
      </aside>
      <main className="relative flex items-center justify-center bg-canvas px-4 py-10">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-brand via-emerald-400 to-accent" aria-hidden />
        <div className="w-full max-w-md">
          <div className="mb-6 flex items-center justify-center gap-3 lg:hidden">
            <LogoMark size={40} /><span className="text-xl font-bold text-navy-800">{APP_NAME}</span>
          </div>
          <div className="card p-8 shadow-xl">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
            {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
            <div className="mt-6">{children}</div>
          </div>
          <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-slate-400"><ShieldCheck className="h-3.5 w-3.5" aria-hidden />Secure sign-in · © {new Date().getFullYear()} {APP_NAME}</p>
        </div>
      </main>
    </div>
  )
}
