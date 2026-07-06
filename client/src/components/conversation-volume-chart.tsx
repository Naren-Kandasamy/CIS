import { cn } from "@/lib/utils";
import { type ComponentProps, useId } from "react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis, ResponsiveContainer } from "recharts";
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
import { Delta, DeltaIcon, DeltaValue } from "@/components/delta";

type TrendRow = {
	name: string;
	value: number;
};

const DEFAULT_DATA: TrendRow[] = [
	{ name: "Jan", value: 40 },
	{ name: "Feb", value: 30 },
	{ name: "Mar", value: 20 },
	{ name: "Apr", value: 27 },
	{ name: "May", value: 18 },
	{ name: "Jun", value: 23 },
	{ name: "Jul", value: 34 },
];

const chartConfig = {
	value: {
		label: "Incidents",
	},
	conversations: {
		label: "Incidents",
		color: "var(--chart-1)",
	},
} satisfies ChartConfig;

interface ConversationVolumeChartProps extends ComponentProps<typeof Card> {
  visualization?: any;
}

export function ConversationVolumeChart({
	className,
  visualization,
	...props
}: ConversationVolumeChartProps) {
	const idAreaGradient = useId();
  
  const trendData = visualization?.recharts?.trend && visualization.recharts.trend.length > 0 
    ? visualization.recharts.trend 
    : DEFAULT_DATA;

  // Map key names if they are different (e.g. name -> date, value -> conversations)
  const chartRows = trendData.map((row: any) => ({
    date: row.name,
    conversations: row.value
  }));

	return (
		<div
			className={cn(
				"shadow-sm md:col-span-2 lg:col-span-3 bg-card border border-border rounded-2xl flex flex-col gap-6",
				className
			)}
			style={{ padding: '28px' }}
		>
			<div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
				<div className="min-w-0 space-y-1">
					<div className="flex flex-wrap items-center gap-2">
						<h3 className="text-foreground text-lg font-semibold">Crime Trends</h3>
						<Delta value={12.4} variant="badge">
							<DeltaIcon variant="trend" />
							<DeltaValue />
						</Delta>
					</div>
					<p className="text-muted-foreground text-sm">
						Monthly registered incident counts in selected window.
					</p>
				</div>
			</div>
			<div>
				<ChartContainer className="aspect-22/8 w-full min-h-[220px]" config={chartConfig}>
					<AreaChart
						accessibilityLayer
						data={chartRows}
						margin={{ left: 0, right: 8, top: 8, bottom: 0 }}
					>
						<defs>
							<linearGradient id={idAreaGradient} x1="0" x2="0" y1="0" y2="1">
								<stop
									offset="0%"
									stopColor="var(--primary)"
									stopOpacity={0.4}
								/>
								<stop
									offset="60%"
									stopColor="var(--primary)"
									stopOpacity={0.1}
								/>
								<stop
									offset="100%"
									stopColor="var(--primary)"
									stopOpacity={0}
								/>
							</linearGradient>
						</defs>
						<CartesianGrid className="stroke-border/40" vertical={false} />
						<XAxis
							axisLine={false}
							dataKey="date"
							tickLine={false}
							tickMargin={8}
              tick={{ className: "text-muted-foreground text-[11px] font-semibold" }}
						/>
						<YAxis
							axisLine={false}
							tick={{ className: "tabular-nums text-muted-foreground text-[10px]" }}
							tickLine={false}
							tickMargin={8}
							width={28}
						/>
						<ChartTooltip
							content={
								<ChartTooltipContent
									className="min-w-32 bg-card border border-border text-foreground"
									indicator="line"
								/>
							}
							cursor={false}
						/>
						<Area
							dataKey="conversations"
							dot={true}
							fill={`url(#${idAreaGradient})`}
							stroke="var(--primary)"
							strokeWidth={2}
							type="natural"
						/>
					</AreaChart>
				</ChartContainer>
			</div>
		</div>
	);
}
export default ConversationVolumeChart;
