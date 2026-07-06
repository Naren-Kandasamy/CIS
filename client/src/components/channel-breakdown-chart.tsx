import { cn } from "@/lib/utils";
import type { ComponentProps } from "react";
import { LabelList, Pie, PieChart, Cell } from "recharts";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	type ChartConfig,
	ChartContainer,
	ChartTooltip,
	ChartTooltipContent,
} from "@/components/ui/chart";

type CrimeDatum = {
	channel: string;
	share: number;
	fill: string;
};

const DEFAULT_DATA: CrimeDatum[] = [
	{ channel: "theft", share: 33, fill: "var(--chart-1)" },
	{ channel: "burglary", share: 17, fill: "var(--chart-4)" },
	{ channel: "assault", share: 25, fill: "var(--chart-3)" },
	{ channel: "fraud", share: 25, fill: "var(--chart-2)" },
];

const chartConfig = {
	share: {
		label: "Share",
	},
	theft: {
		label: "Theft",
		color: "var(--chart-1)",
	},
	burglary: {
		label: "Burglary",
		color: "var(--chart-4)",
	},
	assault: {
		label: "Assault",
		color: "var(--chart-3)",
	},
	fraud: {
		label: "Fraud",
		color: "var(--chart-2)",
	},
} satisfies ChartConfig;

interface ChannelBreakdownChartProps extends ComponentProps<typeof Card> {
  visualization?: any;
}

export function ChannelBreakdownChart({
	className,
  visualization,
	...props
}: ChannelBreakdownChartProps) {
  
  const donutData = visualization?.recharts?.donut && visualization.recharts.donut.length > 0 
    ? visualization.recharts.donut 
    : [];

  let chartData: CrimeDatum[] = [];
  if (donutData.length > 0) {
    const total = donutData.reduce((acc: number, curr: any) => acc + (curr.value || 0), 0) || 1;
    chartData = donutData.map((d: any, idx: number) => {
      const typeLower = (d.name || "").toLowerCase();
      let colorClass = "var(--chart-1)";
      let key = "theft";
      
      if (typeLower.includes("theft")) {
        colorClass = "var(--chart-1)";
        key = "theft";
      } else if (typeLower.includes("burg")) {
        colorClass = "var(--chart-4)";
        key = "burglary";
      } else if (typeLower.includes("ass")) {
        colorClass = "var(--chart-3)";
        key = "assault";
      } else if (typeLower.includes("fraud")) {
        colorClass = "var(--chart-2)";
        key = "fraud";
      } else {
        colorClass = `var(--chart-${(idx % 5) + 1})`;
        key = typeLower;
      }

      return {
        channel: key,
        share: Math.round(((d.value || 0) / total) * 100),
        fill: colorClass
      };
    });
  } else {
    chartData = DEFAULT_DATA;
  }

	return (
		<div
			className={cn("flex flex-col bg-card border border-border rounded-2xl shadow-sm gap-5", className)}
			style={{ padding: '28px' }}
		>
			<div className="space-y-1">
				<h3 className="text-foreground text-lg font-semibold">Crime Distribution</h3>
				<p className="text-muted-foreground text-sm">
					Breakdown of incidents by category.
				</p>
			</div>
			<div className="flex-1 min-h-[220px] flex flex-col items-center justify-center w-full">
				<ChartContainer
					className="mx-auto aspect-square h-[200px] w-[200px]"
					config={chartConfig}
				>
					<PieChart>
						<ChartTooltip
							cursor={false}
							content={
								<ChartTooltipContent
									className="bg-card border border-border text-foreground text-xs py-1.5 px-2.5 rounded-lg"
									formatter={(value, name) => {
										const configEntry = chartConfig[name as keyof typeof chartConfig];
										const label = configEntry ? configEntry.label : String(name);
										return (
											<div className="flex items-center gap-1.5 text-xs text-foreground">
												<span className="font-semibold capitalize">{label}:</span>
												<span className="font-mono text-muted-foreground">{value}%</span>
											</div>
										);
									}}
									hideLabel
								/>
							}
						/>
						<Pie
							data={chartData}
							dataKey="share"
							innerRadius={55}
							outerRadius={80}
							nameKey="channel"
							strokeWidth={3}
							stroke="var(--card)"
						>
							{chartData.map((entry, index) => (
								<Cell key={`cell-${index}`} fill={entry.fill} />
							))}
							<LabelList
								dataKey="share"
								formatter={(label) => {
									const n = Number(label);
									return Number.isFinite(n) ? `${n}%` : String(label ?? "");
								}}
								position="outside"
								fill="var(--foreground)"
								className="text-[10px] font-bold"
							/>
						</Pie>
					</PieChart>
				</ChartContainer>
				{/* Custom Legend stacked in a single column */}
				<div className="flex flex-col gap-2 mt-6 text-foreground text-sm capitalize font-semibold w-fit mx-auto">
					{chartData.map((entry, index) => {
						const configEntry = chartConfig[entry.channel as keyof typeof chartConfig];
						const label = configEntry ? configEntry.label : entry.channel;
						return (
							<div key={index} className="flex items-center gap-2">
								<div
									className="h-2.5 w-2.5 rounded-[2px] shrink-0"
									style={{ backgroundColor: entry.fill }}
								/>
								<span>{label}</span>
							</div>
						);
					})}
				</div>
			</div>
		</div>
	);
}
export default ChannelBreakdownChart;
