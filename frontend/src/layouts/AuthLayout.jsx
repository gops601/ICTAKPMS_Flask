import { CheckCircle2 } from 'lucide-react'
import { HeroIllustration, LogoMark } from '../components/illustrations'
import { APP_NAME, APP_TAGLINE } from '../utils/brand'

const FEATURES = ['SRS submission, review and approval', 'Scrum boards with weekly mentor evaluations', 'Live dashboards and batch-wise reports']

/** Two-panel sign-in shell. Set VITE_HERO_IMAGE to show your own photo/artwork instead of the built-in illustration. */
export default function AuthLayout({ title, subtitle, children }) {
  const heroImage = import.meta.env.VITE_HERO_IMAGE
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <aside className="hero-gradient relative hidden flex-col justify-between overflow-hidden p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <LogoMark size={44} />
          <div><div className="text-2xl font-bold tracking-tight">{APP_NAME}</div><div className="text-sm text-indigo-200">{APP_TAGLINE}</div></div>
        </div>
        <div>
          <h2 className="max-w-md text-3xl font-semibold leading-tight">From problem statement to final evaluation, in one place.</h2>
          {heroImage
            ? <img src={heroImage} alt="" className="mt-6 max-h-[340px] w-full rounded-2xl object-cover shadow-2xl" />
            : <HeroIllustration className="mt-4 w-full max-w-lg" />}
        </div>
        <ul className="space-y-2 text-sm text-indigo-100">
          {FEATURES.map((f) => <li key={f} className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-teal-300" aria-hidden />{f}</li>)}
        </ul>
      </aside>
      <main className="flex items-center justify-center bg-canvas px-4 py-10">
        <div className="w-full max-w-md">
          <div className="mb-6 flex items-center justify-center gap-3 lg:hidden">
            <LogoMark size={40} /><span className="text-xl font-bold text-navy-800">{APP_NAME}</span>
          </div>
          <div className="card p-8">
            <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
            {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
            <div className="mt-6">{children}</div>
          </div>
          <p className="mt-6 text-center text-xs text-slate-400">© {new Date().getFullYear()} {APP_NAME}</p>
        </div>
      </main>
    </div>
  )
}
