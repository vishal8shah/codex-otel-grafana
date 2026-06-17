param(
    [string]$GrafanaUrl = "http://localhost:3000",
    [string]$User = "admin",
    [string]$Password = "admin",
    [string]$FolderUid = "codex-observability",
    [string]$ServiceName = "Codex Desktop"
)

$ErrorActionPreference = "Stop"

$pair = "${User}:${Password}"
$auth = "Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
$Headers = @{ Authorization = $auth }

function Invoke-GrafanaApi {
    param(
        [ValidateSet("GET", "POST")]
        [string]$Method,
        [string]$Path,
        [object]$Body
    )

    $uri = "$GrafanaUrl$Path"
    if ($Body) {
        $json = $Body | ConvertTo-Json -Depth 100
        return Invoke-RestMethod -Method $Method -Uri $uri -Headers $Headers -ContentType "application/json" -Body $json
    }

    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $Headers
}

function New-GridPos {
    param([int]$X, [int]$Y, [int]$W, [int]$H)
    return @{ x = $X; y = $Y; w = $W; h = $H }
}

function New-Datasource {
    param([string]$Type, [string]$Uid)
    return @{ type = $Type; uid = $Uid }
}

function New-Target {
    param(
        [string]$RefId,
        [string]$Expr,
        [string]$DatasourceType,
        [string]$DatasourceUid,
        [string]$QueryType = $null,
        [string]$LegendFormat = $null
    )

    $target = @{
        refId = $RefId
        datasource = New-Datasource $DatasourceType $DatasourceUid
    }

    if ($DatasourceType -eq "prometheus") {
        $target.expr = $Expr
        $target.range = $true
        if ($LegendFormat) { $target.legendFormat = $LegendFormat }
    } elseif ($DatasourceType -eq "loki") {
        $target.expr = $Expr
        $target.queryType = if ($QueryType) { $QueryType } else { "range" }
        if ($LegendFormat) { $target.legendFormat = $LegendFormat }
    } elseif ($DatasourceType -eq "tempo") {
        $target.query = $Expr
        $target.queryType = if ($QueryType) { $QueryType } else { "traceql" }
    }

    return $target
}

function New-Panel {
    param(
        [int]$Id,
        [string]$Title,
        [string]$Type,
        [hashtable]$GridPos,
        [string]$DatasourceType,
        [string]$DatasourceUid,
        [array]$Targets,
        [hashtable]$Options = @{},
        [hashtable]$FieldConfig = @{}
    )

    return @{
        id = $Id
        title = $Title
        type = $Type
        gridPos = $GridPos
        datasource = New-Datasource $DatasourceType $DatasourceUid
        targets = $Targets
        options = $Options
        fieldConfig = @{
            defaults = if ($FieldConfig.defaults) { $FieldConfig.defaults } else { @{} }
            overrides = if ($FieldConfig.overrides) { $FieldConfig.overrides } else { @() }
        }
    }
}

function New-DashboardBase {
    param([string]$Title, [string]$Uid)

    return @{
        uid = $Uid
        title = $Title
        tags = @("codex", "opentelemetry", "local")
        timezone = "browser"
        schemaVersion = 39
        version = 0
        refresh = "30s"
        time = @{ from = "now-6h"; to = "now" }
        templating = @{
            list = @(
                @{
                    name = "service"
                    type = "constant"
                    label = "Service"
                    query = $ServiceName
                    current = @{ text = $ServiceName; value = $ServiceName; selected = $true }
                    hide = 0
                }
            )
        }
        annotations = @{ list = @() }
        panels = @()
    }
}

function Publish-Dashboard {
    param([hashtable]$Dashboard)

    $payload = @{
        dashboard = $Dashboard
        folderUid = $FolderUid
        overwrite = $true
        message = "Codex local OTel dashboard refresh"
    }

    $result = Invoke-GrafanaApi -Method POST -Path "/api/dashboards/db" -Body $payload
    Write-Host "$($Dashboard.title): $GrafanaUrl$($result.url)"
}

try {
    Invoke-GrafanaApi -Method GET -Path "/api/health" | Out-Null
} catch {
    throw "Grafana is not reachable at $GrafanaUrl. Start LGTM first with .\observability\start-lgtm.ps1."
}

try {
    Invoke-GrafanaApi -Method GET -Path "/api/folders/$FolderUid" | Out-Null
} catch {
    Invoke-GrafanaApi -Method POST -Path "/api/folders" -Body @{
        uid = $FolderUid
        title = "Codex Observability"
    } | Out-Null
}

$lokiDs = New-Datasource "loki" "loki"
$promDs = New-Datasource "prometheus" "prometheus"
$tempoDs = New-Datasource "tempo" "tempo"

$logQuery = '{service_name="$service"}'
$warnQuery = '{service_name="$service",severity_text=~"WARN|ERROR|FATAL"}'

$loki = New-DashboardBase "Codex / Loki Logs" "codex-loki-logs"
$loki.panels = @(
    (New-Panel 1 "Log records" "stat" (New-GridPos 0 0 6 4) "loki" "loki" @(
        (New-Target "A" 'sum(count_over_time({service_name="$service"}[$__range]))' "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 2 "Warnings and errors" "stat" (New-GridPos 6 0 6 4) "loki" "loki" @(
        (New-Target "A" 'sum(count_over_time({service_name="$service",severity_text=~"WARN|ERROR|FATAL"}[$__range]))' "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 3 "Events by name" "timeseries" (New-GridPos 12 0 12 8) "loki" "loki" @(
        (New-Target "A" 'sum by (event_name) (count_over_time({service_name="$service"}[$__interval]))' "loki" "loki" "range" "{{event_name}}")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" }; tooltip = @{ mode = "multi" } }),
    (New-Panel 4 "Recent Codex logs" "logs" (New-GridPos 0 8 24 10) "loki" "loki" @(
        (New-Target "A" $logQuery "loki" "loki" "range")
    ) @{ showTime = $true; showLabels = $true; wrapLogMessage = $true; sortOrder = "Descending" }),
    (New-Panel 5 "Warning and error detail" "logs" (New-GridPos 0 18 12 9) "loki" "loki" @(
        (New-Target "A" $warnQuery "loki" "loki" "range")
    ) @{ showTime = $true; showLabels = $true; wrapLogMessage = $true; sortOrder = "Descending" }),
    (New-Panel 6 "Token-bearing completions" "logs" (New-GridPos 12 18 12 9) "loki" "loki" @(
        (New-Target "A" '{service_name="$service",event_name="codex.sse_event"}' "loki" "loki" "range")
    ) @{ showTime = $true; showLabels = $true; wrapLogMessage = $true; sortOrder = "Descending" })
)

$tempo = New-DashboardBase "Codex / Tempo Traces" "codex-tempo-traces"
$tempo.panels = @(
    (New-Panel 1 "Span rate" "timeseries" (New-GridPos 0 0 12 8) "prometheus" "prometheus" @(
        (New-Target "A" 'sum by (span_name) (rate(traces_spanmetrics_calls_total{service="$service"}[$__rate_interval]))' "prometheus" "prometheus" $null "{{span_name}}")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" }; tooltip = @{ mode = "multi" } }),
    (New-Panel 2 "p95 span latency" "timeseries" (New-GridPos 12 0 12 8) "prometheus" "prometheus" @(
        (New-Target "A" 'topk(10, histogram_quantile(0.95, sum by (le, span_name) (rate(traces_spanmetrics_latency_bucket{service="$service"}[$__rate_interval]))))' "prometheus" "prometheus" $null "{{span_name}}")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" }; tooltip = @{ mode = "multi" } } @{ defaults = @{ unit = "s" } }),
    (New-Panel 3 "Spans by kind" "barchart" (New-GridPos 0 8 8 8) "prometheus" "prometheus" @(
        (New-Target "A" 'sum by (span_kind) (increase(traces_spanmetrics_calls_total{service="$service"}[$__range]))' "prometheus" "prometheus" $null "{{span_kind}}")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" } }),
    (New-Panel 4 "Status code breakdown" "timeseries" (New-GridPos 8 8 8 8) "prometheus" "prometheus" @(
        (New-Target "A" 'sum by (status_code) (rate(traces_spanmetrics_calls_total{service="$service"}[$__rate_interval]))' "prometheus" "prometheus" $null "{{status_code}}")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" } }),
    (New-Panel 5 "Service graph requests" "timeseries" (New-GridPos 16 8 8 8) "prometheus" "prometheus" @(
        (New-Target "A" 'sum by (client, server) (rate(traces_service_graph_request_total{server="$service"}[$__rate_interval]))' "prometheus" "prometheus" $null "{{client}} -> {{server}}")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" } }),
    (New-Panel 6 "Trace search" "table" (New-GridPos 0 16 24 10) "tempo" "tempo" @(
        (New-Target "A" '{ resource.service.name = "$service" }' "tempo" "tempo" "traceql")
    ) @{ showHeader = $true })
)

$prom = New-DashboardBase "Codex / Prometheus Metrics" "codex-prometheus-metrics"
$prom.panels = @(
    (New-Panel 1 "OTLP logs accepted" "stat" (New-GridPos 0 0 6 4) "prometheus" "prometheus" @(
        (New-Target "A" 'sum(increase(otelcol_receiver_accepted_log_records_total{receiver="otlp",transport="http"}[$__range]))' "prometheus" "prometheus")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 2 "OTLP spans accepted" "stat" (New-GridPos 6 0 6 4) "prometheus" "prometheus" @(
        (New-Target "A" 'sum(increase(otelcol_receiver_accepted_spans_total{receiver="otlp",transport="http"}[$__range]))' "prometheus" "prometheus")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 3 "OTLP metric points accepted" "stat" (New-GridPos 12 0 6 4) "prometheus" "prometheus" @(
        (New-Target "A" 'sum(increase(otelcol_receiver_accepted_metric_points_total{receiver="otlp",transport="http"}[$__range]))' "prometheus" "prometheus")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 4 "LGTM target health" "stat" (New-GridPos 18 0 6 4) "prometheus" "prometheus" @(
        (New-Target "A" 'sum(up)' "prometheus" "prometheus")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 5 "Top span throughput" "timeseries" (New-GridPos 0 4 12 8) "prometheus" "prometheus" @(
        (New-Target "A" 'topk(12, sum by (span_name) (rate(traces_spanmetrics_calls_total{service="$service"}[$__rate_interval])))' "prometheus" "prometheus" $null "{{span_name}}")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" }; tooltip = @{ mode = "multi" } }),
    (New-Panel 6 "Top p95 span latency" "timeseries" (New-GridPos 12 4 12 8) "prometheus" "prometheus" @(
        (New-Target "A" 'topk(12, histogram_quantile(0.95, sum by (le, span_name) (rate(traces_spanmetrics_latency_bucket{service="$service"}[$__rate_interval]))))' "prometheus" "prometheus" $null "{{span_name}}")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" }; tooltip = @{ mode = "multi" } } @{ defaults = @{ unit = "s" } }),
    (New-Panel 7 "Collector memory" "timeseries" (New-GridPos 0 12 12 8) "prometheus" "prometheus" @(
        (New-Target "A" 'otelcol_process_memory_rss' "prometheus" "prometheus" $null "RSS")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" } } @{ defaults = @{ unit = "bytes" } }),
    (New-Panel 8 "Exporter failures" "timeseries" (New-GridPos 12 12 12 8) "prometheus" "prometheus" @(
        (New-Target "A" 'sum by (exporter) (rate(otelcol_exporter_send_failed_metric_points_total[$__rate_interval]))' "prometheus" "prometheus" $null "{{exporter}}")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" } })
)

$tokens = New-DashboardBase "Codex / Token Economics" "codex-token-economics"
$completionSelector = '{service_name="$service"} | event_name="codex.sse_event" | event_kind="response.completed"'
$inputRatePerMillion = 5
$cachedInputRatePerMillion = 0.5
$outputRatePerMillion = 30
$inputCostExpr = "(sum(sum_over_time($completionSelector | unwrap input_token_count [`$__range])) - sum(sum_over_time($completionSelector | unwrap cached_token_count [`$__range]))) * $inputRatePerMillion / 1000000"
$cachedCostExpr = "sum(sum_over_time($completionSelector | unwrap cached_token_count [`$__range])) * $cachedInputRatePerMillion / 1000000"
$outputCostExpr = "sum(sum_over_time($completionSelector | unwrap output_token_count [`$__range])) * $outputRatePerMillion / 1000000"
$totalCostExpr = "(($inputCostExpr) + ($cachedCostExpr) + ($outputCostExpr))"
$cacheSavingsExpr = "sum(sum_over_time($completionSelector | unwrap cached_token_count [`$__range])) * ($inputRatePerMillion - $cachedInputRatePerMillion) / 1000000"
$intervalCostExpr = "(((sum(sum_over_time($completionSelector | unwrap input_token_count [`$__interval])) - sum(sum_over_time($completionSelector | unwrap cached_token_count [`$__interval]))) * $inputRatePerMillion) + (sum(sum_over_time($completionSelector | unwrap cached_token_count [`$__interval])) * $cachedInputRatePerMillion) + (sum(sum_over_time($completionSelector | unwrap output_token_count [`$__interval])) * $outputRatePerMillion)) / 1000000"
$tokens.panels = @(
    (New-Panel 1 "Input tokens" "stat" (New-GridPos 0 0 4 4) "loki" "loki" @(
        (New-Target "A" "sum(sum_over_time($completionSelector | unwrap input_token_count [`$__range]))" "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 2 "Output tokens" "stat" (New-GridPos 4 0 4 4) "loki" "loki" @(
        (New-Target "A" "sum(sum_over_time($completionSelector | unwrap output_token_count [`$__range]))" "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 3 "Cached tokens" "stat" (New-GridPos 8 0 4 4) "loki" "loki" @(
        (New-Target "A" "sum(sum_over_time($completionSelector | unwrap cached_token_count [`$__range]))" "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 4 "Reasoning tokens" "stat" (New-GridPos 12 0 4 4) "loki" "loki" @(
        (New-Target "A" "sum(sum_over_time($completionSelector | unwrap reasoning_token_count [`$__range]))" "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 5 "Tool tokens" "stat" (New-GridPos 16 0 4 4) "loki" "loki" @(
        (New-Target "A" "sum(sum_over_time($completionSelector | unwrap tool_token_count [`$__range]))" "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 6 "Completions" "stat" (New-GridPos 20 0 4 4) "loki" "loki" @(
        (New-Target "A" "sum(count_over_time($completionSelector [`$__range]))" "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" }),
    (New-Panel 7 "Estimated total cost" "stat" (New-GridPos 0 4 6 4) "loki" "loki" @(
        (New-Target "A" $totalCostExpr "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" } @{ defaults = @{ unit = "currencyUSD" } }),
    (New-Panel 8 "Estimated input cost" "stat" (New-GridPos 6 4 6 4) "loki" "loki" @(
        (New-Target "A" "(($inputCostExpr) + ($cachedCostExpr))" "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" } @{ defaults = @{ unit = "currencyUSD" } }),
    (New-Panel 9 "Estimated output cost" "stat" (New-GridPos 12 4 6 4) "loki" "loki" @(
        (New-Target "A" $outputCostExpr "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" } @{ defaults = @{ unit = "currencyUSD" } }),
    (New-Panel 10 "Estimated cache savings" "stat" (New-GridPos 18 4 6 4) "loki" "loki" @(
        (New-Target "A" $cacheSavingsExpr "loki" "loki" "range")
    ) @{ reduceOptions = @{ calcs = @("lastNotNull") }; orientation = "auto" } @{ defaults = @{ unit = "currencyUSD" } }),
    (New-Panel 11 "Cost trend" "timeseries" (New-GridPos 0 8 24 8) "loki" "loki" @(
        (New-Target "A" $intervalCostExpr "loki" "loki" "range" "estimated USD")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" }; tooltip = @{ mode = "multi" } } @{ defaults = @{ unit = "currencyUSD" } }),
    (New-Panel 12 "Token trend by type" "timeseries" (New-GridPos 0 16 16 9) "loki" "loki" @(
        (New-Target "A" "sum(sum_over_time($completionSelector | unwrap input_token_count [`$__interval]))" "loki" "loki" "range" "input")
        (New-Target "B" "sum(sum_over_time($completionSelector | unwrap output_token_count [`$__interval]))" "loki" "loki" "range" "output")
        (New-Target "C" "sum(sum_over_time($completionSelector | unwrap cached_token_count [`$__interval]))" "loki" "loki" "range" "cached")
        (New-Target "D" "sum(sum_over_time($completionSelector | unwrap reasoning_token_count [`$__interval]))" "loki" "loki" "range" "reasoning")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" }; tooltip = @{ mode = "multi" } }),
    (New-Panel 13 "Token mix" "barchart" (New-GridPos 16 16 8 9) "loki" "loki" @(
        (New-Target "A" "sum(sum_over_time($completionSelector | unwrap input_token_count [`$__range]))" "loki" "loki" "range" "input")
        (New-Target "B" "sum(sum_over_time($completionSelector | unwrap output_token_count [`$__range]))" "loki" "loki" "range" "output")
        (New-Target "C" "sum(sum_over_time($completionSelector | unwrap cached_token_count [`$__range]))" "loki" "loki" "range" "cached")
        (New-Target "D" "sum(sum_over_time($completionSelector | unwrap reasoning_token_count [`$__range]))" "loki" "loki" "range" "reasoning")
        (New-Target "E" "sum(sum_over_time($completionSelector | unwrap tool_token_count [`$__range]))" "loki" "loki" "range" "tool")
    ) @{ legend = @{ showLegend = $true; placement = "bottom" } }),
    (New-Panel 14 "Pricing assumptions" "text" (New-GridPos 0 25 8 6) "loki" "loki" @() @{
        mode = "markdown"
        content = "Estimated USD uses configurable script defaults: input `$5.00/M`, cached input `$0.50/M`, output `$30.00/M`. Recheck official pricing before budgeting."
    }),
    (New-Panel 15 "Completion records" "logs" (New-GridPos 8 25 16 9) "loki" "loki" @(
        (New-Target "A" $completionSelector "loki" "loki" "range")
    ) @{ showTime = $true; showLabels = $true; wrapLogMessage = $true; sortOrder = "Descending" })
)

Publish-Dashboard $loki
Publish-Dashboard $tempo
Publish-Dashboard $prom
Publish-Dashboard $tokens
