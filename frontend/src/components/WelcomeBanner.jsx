import { useAuth } from '../context/AuthContext'
import { BannerArt } from './illustrations'

const MESSAGES = {
  admin: 'Here is the institution at a glance.',
  domain_lead: "Here's how your domain is progressing.",
  mentor: "Here's what needs your attention today.",
  student: 'Keep going – here is where your project stands.',
}

const greeting = () => {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

/** Gradient greeting card shown at the top of every dashboard. */
export default function WelcomeBanner({ extra }) {
  const { user } = useAuth()
  const first = (user.name || '').split(' ')[0]
  return (
    <section className="banner-gradient relative overflow-hidden rounded-2xl p-6 text-white shadow-soft" aria-label="Welcome">
      <BannerArt className="pointer-events-none absolute -right-4 bottom-0 hidden h-full w-72 sm:block" />
      <div className="relative max-w-xl">
        <h2 className="text-xl font-semibold sm:text-2xl">{greeting()}, {first}!</h2>
        <p className="mt-1 text-sm text-indigo-100">{MESSAGES[user.role]}</p>
        {extra && <div className="mt-3">{extra}</div>}
      </div>
    </section>
  )
}
