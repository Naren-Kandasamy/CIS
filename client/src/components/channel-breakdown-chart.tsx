import { cn } from "@/lib/utils";
import type { ComponentProps } from "react";
import { LabelList, Pie, PieChart } from "recharts";
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
	ChartLegend,
	ChartLegendContent,
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
			className={cn("flex flex-col bg-[#13131a]/40 border border-white/5 rounded-2xl shadow-xl backdrop-blur-md gap-5", className)}
			style={{ padding: '28px' }}
		>
			<div className="space-y-1">
				<h3 className="text-white text-lg font-semibold">Crime Distribution</h3>
				<p className="text-zinc-400 text-sm">
					Breakdown of incidents by category.
				</p>
			</div>
			<div className="flex-1 min-h-[220px] flex items-center justify-center w-full">
				<ChartContainer
					className="mx-auto h-[200px] w-[200px]"
					config={chartConfig}
				>
					<PieChart>
						<ChartTooltip
							cursor={false}
							content={
								<ChartTooltipContent
									className="bg-zinc-950 border border-white/10 text-white text-xs py-1.5 px-2.5 rounded-lg"
									formatter={(value, name) => {
										const configEntry = chartConfig[name as keyof typeof chartConfig];
										const label = configEntry ? configEntry.label : String(name);
										return (
											<div className="flex items-center gap-1.5 text-xs text-white">
												<span className="font-semibold capitalize">{label}:</span>
												<span className="font-mono text-zinc-300">{value}%</span>
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
							nameKey="channel"
							strokeWidth={3}
							stroke="var(--card)"
						>
							<LabelList
								dataKey="share"
								formatter={(label) => {
									const n = Number(label);
									return Number.isFinite(n) ? `${n}%` : String(label ?? "");
								}}
								position="outside"
								className="fill-zinc-400 text-[10px] font-semibold"
							/>
						</Pie>
						<ChartLegend
							className="-translate-y-2 flex-wrap gap-x-2.5 gap-y-1.5 text-zinc-400 text-xs capitalize font-semibold"
							content={<ChartLegendContent nameKey="channel" />}
						/>
					</PieChart>
				</ChartContainer>
			</div>
		</div>
	);
}
export default ChannelBreakdownChart;
