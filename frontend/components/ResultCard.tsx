interface Props {
  title: string;
  content: string;
  accent: string; // tailwind color class like 'border-green-500'
  icon?: string;
}

export default function ResultCard({ title, content, accent, icon }: Props) {
  return (
    <div className={`bg-[#161b22] border-l-4 ${accent} rounded-lg p-4`}>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-[#8b949e] mb-2">
        {icon && <span className="mr-1">{icon}</span>}{title}
      </h3>
      <p className="text-[#f0f6fc] text-sm leading-relaxed">{content}</p>
    </div>
  );
}
