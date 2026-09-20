export type ChartSlice = {
  label: string;
  value: number;
  color: string;
};

export function DonutChart({ items }: { items: ChartSlice[] }) {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="flex items-center gap-6">
      <svg width="120" height="120" viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="60" r={radius} fill="none" stroke="#e4ddd2" strokeWidth="14" />
        {total > 0
          ? items
              .filter((item) => item.value > 0)
              .map((item) => {
                const length = (item.value / total) * circumference;
                const circle = (
                  <circle
                    key={item.label}
                    cx="60"
                    cy="60"
                    r={radius}
                    fill="none"
                    stroke={item.color}
                    strokeWidth="14"
                    strokeDasharray={`${length} ${circumference - length}`}
                    strokeDashoffset={-offset}
                    strokeLinecap="butt"
                    transform="rotate(-90 60 60)"
                  />
                );
                offset += length;
                return circle;
              })
          : null}
        <text
          x="60"
          y="56"
          textAnchor="middle"
          className="fill-ink"
          style={{ fontSize: "22px", fontWeight: 600 }}
        >
          {total}
        </text>
        <text x="60" y="74" textAnchor="middle" className="fill-muted" style={{ fontSize: "10px" }}>
          files
        </text>
      </svg>
      <ul className="space-y-2 text-sm">
        {items.map((item) => (
          <li key={item.label} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: item.color }} />
            <span className="text-muted">{item.label}</span>
            <span className="ml-auto font-medium tabular-nums">{item.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BarList({
  items,
  empty = "No data yet.",
}: {
  items: ChartSlice[];
  empty?: string;
}) {
  const max = Math.max(...items.map((item) => item.value), 1);
  return (
    <div className="space-y-3">
      {items.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted">{empty}</p>
      ) : (
        items.map((item) => (
          <div key={item.label}>
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="capitalize text-muted">{item.label}</span>
              <span className="tabular-nums font-medium">{item.value}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.max(6, (item.value / max) * 100)}%`,
                  background: item.color,
                }}
              />
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export function ColumnChart({
  items,
}: {
  items: { label: string; value: number }[];
}) {
  const max = Math.max(...items.map((item) => item.value), 1);
  return (
    <div className="flex h-44 items-end gap-1.5">
      {items.map((item) => (
        <div key={item.label} className="flex min-w-0 flex-1 flex-col items-center gap-2">
          <div className="flex h-32 w-full items-end">
            <div
              className="w-full rounded-t-md bg-void/85"
              style={{ height: `${Math.max(item.value > 0 ? 8 : 2, (item.value / max) * 100)}%` }}
              title={`${item.label}: ${item.value}`}
            />
          </div>
          <span className="text-[10px] tracking-wide text-muted">{item.label}</span>
        </div>
      ))}
    </div>
  );
}
