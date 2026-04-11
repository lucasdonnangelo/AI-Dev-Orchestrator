export default function Header({ title, subtitle }) {
  return (
    <header className="h-14 bg-gray-950 border-b border-gray-800 flex items-center px-6 gap-3 shrink-0">
      <h1 className="text-white font-medium text-base leading-none">{title}</h1>
      {subtitle && (
        <>
          <span className="text-gray-600">/</span>
          <span className="text-gray-400 text-sm">{subtitle}</span>
        </>
      )}
    </header>
  )
}
