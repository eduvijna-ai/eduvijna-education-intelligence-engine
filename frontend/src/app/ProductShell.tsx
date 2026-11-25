import { NavLink, Outlet } from 'react-router-dom'

import { DESIGN_ROLE_FIXTURES } from '../fixtures/catalogue'
import { NonAuthoritativeBanner } from './NonAuthoritativeBanner'

const NAV = [
  { to: '/', label: 'Foundation', end: true },
  { to: '/studio', label: 'Question studio' },
  { to: '/student', label: 'Student runner' },
  { to: '/results', label: 'Student results' },
  { to: '/diagnostics/teacher', label: 'Teacher diagnostics' },
  { to: '/diagnostics/student', label: 'Student diagnostics' },
  { to: '/remediation', label: 'Remediation' },
  { to: '/knowledge', label: 'Knowledge library' },
  { to: '/sources', label: 'Sources' },
  { to: '/onboarding', label: 'Pack onboarding' },
  { to: '/policy', label: 'Policy & API' },
  { to: '/auth-design', label: 'Auth (design)' },
]

export function ProductShell() {
  return (
    <div className="product-layout">
      <NonAuthoritativeBanner />
      <header className="product-header">
        <p className="eyebrow">EDUVIJNA</p>
        <h1 className="product-title">Education Intelligence — product surfaces</h1>
        <nav className="role-nav" aria-label="Design role fixtures (non-authoritative)">
          {DESIGN_ROLE_FIXTURES.map((role) => (
            <span key={role.id} className="role-chip" data-design-role={role.id}>
              {role.label}
            </span>
          ))}
        </nav>
      </header>
      <div className="product-body">
        <nav className="side-nav" aria-label="Primary">
          <ul>
            {NAV.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end} className={({ isActive }) => (isActive ? 'active' : '')}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <main className="product-main" id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}