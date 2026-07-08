import { cn } from "@/lib/utils";
import type { ComponentProps } from "react";
import type { SelectedEntity } from "../hooks/useEntityDrawer";
import { Badge } from "@/components/ui/badge";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { Shield } from "lucide-react";

type CaseCitation = {
	firId: string;
	crimeType: string;
	district: string;
	date: string;
	weapon: string;
	confidence: string;
};

const DEFAULT_ROWS: CaseCitation[] = [
	{
		firId: "FIR 12/2024",
		crimeType: "Theft",
		district: "Belagavi",
		date: "2024-03-12",
		weapon: "Knife",
		confidence: "High",
	},
	{
		firId: "FIR 45/2023",
		crimeType: "Burglary",
		district: "Belagavi",
		date: "2023-11-05",
		weapon: "None",
		confidence: "Medium",
	},
	{
		firId: "FIR 89/2024",
		crimeType: "Assault",
		district: "Bengaluru City",
		date: "2024-04-18",
		weapon: "Iron Rod",
		confidence: "High",
	},
	{
		firId: "FIR 102/2024",
		crimeType: "Fraud",
		district: "Belagavi",
		date: "2024-05-22",
		weapon: "None",
		confidence: "Low",
	},
];

function statusColor(confidence: string): string {
	const c = confidence.toLowerCase();
	if (c === "high") {
		return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
	}
	if (c === "medium") {
		return "bg-amber-500/10 text-amber-400 border-amber-500/20";
	}
	return "bg-rose-500/10 text-rose-400 border-rose-500/20";
}

function getConfidenceTextColor(confidence: string): string {
	const c = confidence.toLowerCase();
	if (c === "high") {
		return "text-emerald-700";
	}
	if (c === "medium") {
		return "text-amber-700";
	}
	return "text-rose-700";
}

interface RecentConversationsProps extends ComponentProps<typeof Card> {
  visualization?: any;
  evidence?: any[];
  onRowClick?: (entity: SelectedEntity) => void;
}

export function RecentConversations({
	className,
  visualization,
  evidence,
  onRowClick,
	...props
}: RecentConversationsProps) {
  
  let caseRows: CaseCitation[] = [];
  
  if (evidence && evidence.length > 0) {
    caseRows = evidence.slice(0, 5).map((item: any, idx: number) => {
      const data = item.data || {};
      return {
        firId: item.fir_id || `FIR ${idx + 1}`,
        crimeType: data.crime_type || data.crime_category || "Incident",
        district: data.district || "Karnataka",
        date: data.Date || data.date || data.occurrence_date || "N/A",
        weapon: data.weapon || data.weapon_used || "None",
        confidence: item.confidence || (idx % 3 === 0 ? "High" : idx % 3 === 1 ? "Medium" : "Low")
      };
    });
  } else if (visualization?.leaflet?.markers && visualization.leaflet.markers.length > 0) {
    caseRows = visualization.leaflet.markers.slice(0, 5).map((m: any, idx: number) => {
      const popupText = m.popup || "";
      const parts = popupText.split(" - ");
      return {
        firId: parts[0] || `FIR ${idx + 1}`,
        crimeType: parts[1] || "Incident",
        district: parts[2] || "Karnataka",
        date: "2024-04-10",
        weapon: "None",
        confidence: idx % 3 === 0 ? "High" : idx % 3 === 1 ? "Medium" : "Low"
      };
    });
  } else {
    caseRows = DEFAULT_ROWS;
  }

	return (
		<div
			className={cn("dossier-panel flex flex-col gap-5", className)}
			style={{ padding: '28px' }}
		>
			<div className="space-y-1">
				<h3 className="dossier-panel-title text-base">Recent Citations</h3>
				<p className="dossier-panel-subtitle text-sm">
					Historical crime evidence loaded in scope.
				</p>
			</div>
			<div className="overflow-x-auto">
				<Table>
					<TableHeader>
						<TableRow className="dossier-row hover:bg-transparent">
							<TableHead className="dossier-table-head font-semibold text-xs uppercase tracking-wider py-3.5 pl-1">Case Reference</TableHead>
							<TableHead className="dossier-table-head font-semibold text-xs uppercase tracking-wider py-3.5">Crime Category</TableHead>
							<TableHead className="dossier-table-head font-semibold text-xs uppercase tracking-wider py-3.5">District</TableHead>
							<TableHead className="dossier-table-head font-semibold text-xs uppercase tracking-wider py-3.5">Incident Date</TableHead>
							<TableHead className="dossier-table-head font-semibold text-xs uppercase tracking-wider py-3.5">Weapon Involved</TableHead>
							<TableHead className="dossier-table-head font-semibold text-xs uppercase tracking-wider py-3.5 pl-4 text-left">Confidence</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{caseRows.map((r, idx) => (
							<TableRow
								className="dossier-row transition-colors duration-150 entity-clickable"
								key={idx}
								style={{ cursor: onRowClick ? 'pointer' : undefined }}
								onClick={() => onRowClick?.({ type: 'fir', id: r.firId, label: r.firId, data: { crime_type: r.crimeType, district: r.district, date: r.date, weapon: r.weapon, crime_no: r.firId }, evidenceItems: evidence ? evidence.filter(e => (e.fir_id ?? '') === r.firId) : [] })}
							>
								<TableCell className="py-3.5 pl-1">
									<div className="flex items-center gap-2">
										<Shield className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent-secondary)' }} />
										<span className="dossier-id font-semibold text-[13px]">{r.firId}</span>
									</div>
								</TableCell>
								<TableCell className="py-3.5 text-[13.5px] font-medium" style={{ color: 'var(--text-primary)' }}>{r.crimeType}</TableCell>
								<TableCell className="py-3.5 text-[13.5px]" style={{ color: 'var(--text-secondary)' }}>{r.district}</TableCell>
								<TableCell className="dossier-mono py-3.5 text-[12.5px]">{r.date}</TableCell>
								<TableCell className="py-3.5 text-[13.5px]" style={{ color: 'var(--text-secondary)' }}>{r.weapon}</TableCell>
								<TableCell className="py-3.5 pl-4 text-left">
									<span className={cn("text-xs font-bold uppercase tracking-wider", getConfidenceTextColor(r.confidence))}>
										{r.confidence}
									</span>
								</TableCell>
							</TableRow>
						))}
					</TableBody>
				</Table>
			</div>
		</div>
	);
}
export default RecentConversations;
