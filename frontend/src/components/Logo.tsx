type LogoSize = 'xs' | 'sm' | 'nav' | 'md' | 'lg' | 'xl'

interface LogoProps {
  size?: LogoSize
  className?: string
}

const heights: Record<LogoSize, string> = {
  xs:  'h-6',   // 24px
  sm:  'h-8',   // 32px
  nav: 'h-9',   // 36px  — headers
  md:  'h-12',  // 48px
  lg:  'h-20',  // 80px
  xl:  'h-28',  // 112px — login brand panel
}

export default function Logo({ size = 'md', className = '' }: LogoProps) {
  return (
    <img
      src="/logo.png"
      alt="Trading Copilot"
      className={`${heights[size]} w-auto object-contain ${className}`}
      draggable={false}
    />
  )
}
