export default function Logo({ className = "w-8 h-8", withText = false, textClassName = "text-xl font-bold text-slate-900 tracking-tight" }) {
  return (
    <div className="flex items-center gap-2">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 120 120"
        className={className}
      >
        <defs>
          <linearGradient id="leafGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#86efac" />
            <stop offset="50%" stopColor="#22c55e" />
            <stop offset="100%" stopColor="#15803d" />
          </linearGradient>
          <linearGradient id="vGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#4ade80" />
            <stop offset="100%" stopColor="#166534" />
          </linearGradient>
        </defs>

        {/* Left arm of the V */}
        <path
          d="M30,30 L55,90 A5,5 0 0,0 63,90 L68,75"
          fill="none"
          stroke="url(#vGradient)"
          strokeWidth="14"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Right leaf part */}
        <path
          d="M58,85 C65,60 80,35 105,25 C100,50 85,80 58,85 Z"
          fill="url(#leafGradient)"
        />
        
        {/* Leaf Veins */}
        <path
          d="M58,85 C65,70 75,55 95,45 M75,60 C85,60 90,55 90,55 M68,72 C75,75 80,75 80,75"
          fill="none"
          stroke="#ffffff"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {withText && <span className={textClassName}>VerdeAI</span>}
    </div>
  )
}
