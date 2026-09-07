import React from 'react'
import { Info, Warning, ShieldCheck, Lightning } from '@phosphor-icons/react'

type CalloutType = 'info' | 'warning' | 'security' | 'invariant'

interface CalloutProps {
  type?: CalloutType
  title?: string
  children: React.ReactNode
}

export const Callout: React.FC<CalloutProps> = ({
  type = 'info',
  title,
  children,
}) => {
  const configs = {
    info: {
      border: 'border-stone-300',
      bg: 'bg-stone-100/70',
      icon: <Info size={18} weight="bold" className="text-stone-700 mt-0.5 shrink-0" />,
      defaultTitle: 'Note',
      titleColor: 'text-stone-900',
    },
    warning: {
      border: 'border-amber-300',
      bg: 'bg-amber-50/80',
      icon: <Warning size={18} weight="bold" className="text-amber-700 mt-0.5 shrink-0" />,
      defaultTitle: 'Attention',
      titleColor: 'text-amber-900',
    },
    security: {
      border: 'border-emerald-300',
      bg: 'bg-emerald-50/70',
      icon: <ShieldCheck size={18} weight="bold" className="text-emerald-700 mt-0.5 shrink-0" />,
      defaultTitle: 'Security Boundary',
      titleColor: 'text-emerald-950',
    },
    invariant: {
      border: 'border-blue-300',
      bg: 'bg-blue-50/70',
      icon: <Lightning size={18} weight="bold" className="text-blue-700 mt-0.5 shrink-0" />,
      defaultTitle: 'Core Invariant',
      titleColor: 'text-blue-950',
    },
  }

  const current = configs[type]

  return (
    <div className={`my-5 rounded-lg border ${current.border} ${current.bg} p-4 text-xs font-body text-stone-800 transition-all`}>
      <div className="flex items-start gap-3">
        {current.icon}
        <div className="flex-1 space-y-1">
          <div className={`font-semibold text-xs tracking-tight ${current.titleColor}`}>
            {title || current.defaultTitle}
          </div>
          <div className="leading-relaxed text-stone-700 space-y-2">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
