import { useState } from 'react'
import { CheckCircle, XCircle, SlidersHorizontal, Info } from '@phosphor-icons/react'

type PolicyMode = 'EXCLUDE' | 'FLAG' | 'STRICT'

export const PolicyCalculator: React.FC = () => {
  const [totalRequested, setTotalRequested] = useState<number>(18)
  const [exposedCount, setExposedCount] = useState<number>(2)
  const [unknownCount, setUnknownCount] = useState<number>(0)
  const [policy, setPolicy] = useState<PolicyMode>('EXCLUDE')
  const [passedCount, setPassedCount] = useState<number>(14)

  // Calculations
  const cleanCount = Math.max(0, totalRequested - exposedCount - unknownCount)

  let evaluatedTasks = 0
  let excludedTasks = 0
  let cleanClaimPermitted = false
  let verdictReason = ''

  if (policy === 'EXCLUDE') {
    evaluatedTasks = cleanCount
    excludedTasks = exposedCount
    if (unknownCount > 0) {
      cleanClaimPermitted = false
      verdictReason = 'Monitoring history is incomplete. UNKNOWN tasks block a clean claim under fail-closed rules.'
    } else {
      cleanClaimPermitted = true
      verdictReason = 'Exposed tasks cleanly excluded from denominator. Clean claim permitted.'
    }
  } else if (policy === 'FLAG') {
    evaluatedTasks = totalRequested - unknownCount
    excludedTasks = 0
    cleanClaimPermitted = unknownCount === 0
    verdictReason = unknownCount > 0
      ? 'UNKNOWN tasks present: claim blocked.'
      : 'All requested tasks evaluated. Exposed tasks flagged in portable report.'
  } else {
    // STRICT
    if (exposedCount > 0 || unknownCount > 0) {
      evaluatedTasks = 0
      excludedTasks = totalRequested
      cleanClaimPermitted = false
      verdictReason = 'STRICT policy active. Any prior exposure or unknown history immediately halts evaluation.'
    } else {
      evaluatedTasks = totalRequested
      excludedTasks = 0
      cleanClaimPermitted = true
      verdictReason = 'Zero contamination detected across all registered tasks. Strict evaluation clean.'
    }
  }

  const effectivePassed = Math.min(passedCount, evaluatedTasks)
  const calculatedScore = evaluatedTasks > 0 ? (effectivePassed / evaluatedTasks) * 100 : 0

  return (
    <div className="my-6 rounded-xl border border-stone-200/90 bg-white shadow-md p-4 sm:p-6 font-body text-stone-900">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 sm:pb-4 mb-4 sm:mb-5 border-b border-stone-200/80 gap-2">
        <div className="flex items-center gap-2">
          <SlidersHorizontal size={18} weight="bold" className="text-emerald-700 shrink-0" />
          <h3 className="font-heading text-sm sm:text-base font-bold text-stone-900 tracking-tight">
            Interactive Policy & Contamination Calculator
          </h3>
        </div>
        <span className="text-[10px] sm:text-[11px] font-mono text-stone-600 uppercase bg-stone-100 px-2 py-0.5 rounded self-start sm:self-auto">
          Live Policy Simulation
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Controls */}
        <div className="space-y-4 text-xs">
          <div>
            <div className="flex justify-between font-semibold mb-1">
              <span>Total Requested Tasks</span>
              <span className="font-mono text-stone-800">{totalRequested}</span>
            </div>
            <input
              type="range"
              min="5"
              max="50"
              value={totalRequested}
              onChange={(e) => {
                const val = Number(e.target.value)
                setTotalRequested(val)
                if (passedCount > val) setPassedCount(val)
              }}
              className="w-full accent-emerald-700 cursor-pointer"
            />
          </div>

          <div>
            <div className="flex justify-between font-semibold mb-1">
              <span className="text-amber-800">Previously Exposed Tasks</span>
              <span className="font-mono text-amber-800">{exposedCount}</span>
            </div>
            <input
              type="range"
              min="0"
              max={Math.min(10, totalRequested)}
              value={exposedCount}
              onChange={(e) => setExposedCount(Number(e.target.value))}
              className="w-full accent-amber-600 cursor-pointer"
            />
          </div>

          <div>
            <div className="flex justify-between font-semibold mb-1">
              <span className="text-stone-700">Unknown / Incomplete Tasks</span>
              <span className="font-mono text-stone-700">{unknownCount}</span>
            </div>
            <input
              type="range"
              min="0"
              max={5}
              value={unknownCount}
              onChange={(e) => setUnknownCount(Number(e.target.value))}
              className="w-full accent-stone-600 cursor-pointer"
            />
          </div>

          <div>
            <div className="flex justify-between font-semibold mb-1">
              <span className="text-emerald-800">Tasks Passing Evaluator</span>
              <span className="font-mono text-emerald-800">{effectivePassed}</span>
            </div>
            <input
              type="range"
              min="0"
              max={evaluatedTasks || 1}
              value={effectivePassed}
              onChange={(e) => setPassedCount(Number(e.target.value))}
              className="w-full accent-emerald-700 cursor-pointer"
            />
          </div>

          {/* Policy Selector */}
          <div className="pt-2">
            <label className="block font-semibold mb-1.5 text-stone-800">Configured Policy Mode</label>
            <div className="grid grid-cols-3 gap-2">
              {(['EXCLUDE', 'FLAG', 'STRICT'] as PolicyMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setPolicy(mode)}
                  className={`py-1.5 text-xs font-mono rounded border transition-all ${
                    policy === mode
                      ? 'border-emerald-700 bg-emerald-50 font-bold text-emerald-900 shadow-xs'
                      : 'border-stone-300 hover:border-stone-400 text-stone-700 bg-white'
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Results Card */}
        <div className="rounded-lg border border-stone-200 bg-[#fbf9f5] p-5 flex flex-col justify-between">
          <div className="space-y-4 text-xs font-body">
            <div className="flex items-center justify-between pb-3 border-b border-stone-200">
              <span className="text-stone-600">Clean Task Partition</span>
              <span className="font-mono font-bold text-stone-900 text-sm">
                {cleanCount} / {totalRequested} clean
              </span>
            </div>

            <div className="flex items-center justify-between pb-3 border-b border-stone-200">
              <span className="text-stone-600">Evaluated Tasks</span>
              <span className="font-mono font-semibold text-stone-900">
                {evaluatedTasks} tasks
              </span>
            </div>

            <div className="flex items-center justify-between pb-3 border-b border-stone-200">
              <span className="text-stone-600">Excluded Tasks</span>
              <span className="font-mono font-semibold text-amber-800">
                {excludedTasks} tasks
              </span>
            </div>

            <div className="flex items-center justify-between pb-3 border-b border-stone-200">
              <span className="text-stone-600">Calculated Clean Score</span>
              <span className="font-mono font-bold text-base text-emerald-700">
                {calculatedScore.toFixed(1)}% ({effectivePassed}/{evaluatedTasks})
              </span>
            </div>

            <div className="pt-1">
              <span className="block text-stone-600 mb-1.5 font-semibold">Clean Claim Verdict</span>
              <div className={`flex items-center gap-2 p-2.5 rounded border text-xs font-semibold ${
                cleanClaimPermitted
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-950'
                  : 'border-red-200 bg-red-50 text-red-900'
              }`}>
                {cleanClaimPermitted ? (
                  <CheckCircle size={17} weight="fill" className="text-emerald-700 shrink-0" />
                ) : (
                  <XCircle size={17} weight="fill" className="text-red-700 shrink-0" />
                )}
                <span>Clean claim: {cleanClaimPermitted ? 'PERMITTED' : 'DENIED'}</span>
              </div>
            </div>

            <p className="text-[11px] leading-relaxed text-stone-600 mt-2 bg-stone-100/80 p-2.5 rounded border border-stone-200/60">
              <Info size={13} className="inline mr-1 text-stone-600 align-text-bottom" />
              {verdictReason}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
