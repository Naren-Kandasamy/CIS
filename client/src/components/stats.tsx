import { cn } from "@/lib/utils";
import { Delta, DeltaIcon, DeltaValue } from "@/components/delta";

export function DashboardStats({ visualization }: { visualization?: any }) {
  // Compute crime stats dynamically from the search visualization
  const totalCases = visualization?.recharts?.donut?.reduce((acc: number, curr: any) => acc + (curr.value || 0), 0) || 14;
  const suspects = visualization?.cytoscape?.elements?.filter((el: any) => el.data?.type === 'person').length || 8;
  const locationsMapped = visualization?.leaflet?.markers?.length || 10;
  
  // Find the district with maximum occurrences or fallback
  const districts = visualization?.leaflet?.markers?.map((m: any) => {
    const match = m.popup?.match(/FIR .* - (.*)$/);
    return match ? match[1] : null;
  }).filter(Boolean) || [];
  
  const districtCounts: Record<string, number> = {};
  districts.forEach((d: string) => {
    districtCounts[d] = (districtCounts[d] || 0) + 1;
  });
  
  let hotSpot = "Belagavi";
  let maxCount = 0;
  Object.entries(districtCounts).forEach(([d, count]) => {
    if (count > maxCount) {
      maxCount = count;
      hotSpot = d;
    }
  });

  const crimeStats = [
    {
      label: "Retrieved Cases",
      value: String(totalCases),
      delta: 7.2,
      footnote: "vs prior session",
    },
    {
      label: "Accused / Suspects",
      value: String(suspects),
      delta: 14.3,
      footnote: "vs prior session",
    },
    {
      label: "Mapped Incident Scenes",
      value: String(locationsMapped),
      delta: 10.0,
      footnote: "vs prior session",
    },
    {
      label: "Active Hot Spot",
      value: hotSpot,
      delta: -4.5,
      footnote: "crime rate index",
    },
  ];

  return (
    <>
      {crimeStats.map((s) => (
        <div 
          className="bg-card border border-border rounded-2xl shadow-sm flex flex-col justify-between h-full hover:border-border/80 hover:shadow-md transition-all duration-300 gap-3.5"
          style={{ padding: '16px 20px' }}
          key={s.label}
        >
          <div>
            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block leading-normal">
              {s.label}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <p className="font-extrabold text-3xl text-foreground tabular-nums tracking-tight leading-none">
              {s.value}
            </p>
            <div className="flex items-center gap-1.5 text-xs mt-1.5">
              <Delta value={s.delta}>
                <DeltaIcon />
                <DeltaValue />
              </Delta>
              <span className="text-foreground/80 text-[13px] font-bold">{s.footnote}</span>
            </div>
          </div>
        </div>
      ))}
    </>
  );
}
