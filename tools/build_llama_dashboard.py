#!/usr/bin/env python3
"""Build consolidated grafana/dashboards/llama-swap.json.

Replaces: llama_swap_exporter.json (uid llama-swap-unified),
          llamaswap.json (uid complete-llamaswap-dcgm-telemetry),
          DB dashboards llama-swap-full-observability + llamacpp-exact-metrics.

Datasource policy: every panel + target gets an explicit
{"type":"prometheus","uid":"${DS_PROMETHEUS}"} resolved via the DS_PROMETHEUS
datasource template var (query 'prometheus' -> matches provisioned name).

Layout: flat panel list; row panels (h=1) followed by their children in
gridPos order. Each row's children are tracked so y advances past the
tallest child.
"""
import json

DS = {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}
_id = [100]


def nid():
    _id[0] += 1
    return _id[0]


def tgt(expr, legend="", ref="A", **extra):
    t = {
        "datasource": DS,
        "expr": expr,
        "legendFormat": legend,
        "range": True,
        "refId": ref,
    }
    t.update(extra)
    return t


class Row:
    """Collects children with local x/y; emits row + children into the flat list."""

    def __init__(self, out, title, y):
        self.out = out
        self.title = title
        self.y = y
        self.row = {
            "collapse": False,
            "collapsed": False,
            "datasource": DS,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
            "id": nid(),
            "panels": [],
            "title": title,
            "type": "row",
        }
        out.append(self.row)
        self.y += 1
        self.max_h = 0

    def add(self, panel):
        gp = panel["gridPos"]
        # y given relative to row content start
        panel["gridPos"] = {"h": gp["h"], "w": gp["w"], "x": gp["x"], "y": self.y + gp["y"]}
        self.max_h = max(self.max_h, gp["y"] + gp["h"])
        self.out.append(panel)
        return panel

    def end(self):
        return self.y + self.max_h


def stat(title, x, y, expr, unit=None, legend="", w=4, h=4, thresholds=None):
    fc = {
        "defaults": {
            "thresholds": {
                "mode": "absolute",
                "steps": thresholds
                or [{"color": "red", "value": None}, {"color": "green", "value": 0}],
            },
            "unit": unit or "short",
        },
        "overrides": [],
    }
    return {
        "datasource": DS,
        "fieldConfig": fc,
        "id": nid(),
        "title": title,
        "type": "stat",
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "options": {
            "colorMode": "value",
            "graphMode": "none",
            "justifyMode": "auto",
            "orientation": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": "auto",
        },
        "targets": [tgt(expr, legend)],
    }


def ts(title, x, y, targets, unit=None, w=12, h=8, min_=None, max_=None, fill=6, linewidth=1):
    d = {
        "custom": {
            "drawStyle": "line",
            "fillOpacity": fill,
            "lineInterpolation": "linear",
            "lineStyle": {"dash": [], "fill": "solid"},
            "linewidth": linewidth,
            "pointSize": 5,
            "showPoints": "auto",
            "spanNulls": False,
            "stacking": {"group": "A", "mode": "none"},
        },
        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]},
        "unit": unit or "short",
    }
    if min_ is not None:
        d["min"] = min_
    if max_ is not None:
        d["max"] = max_
    return {
        "datasource": DS,
        "fieldConfig": {"defaults": d, "overrides": []},
        "id": nid(),
        "title": title,
        "type": "timeseries",
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "options": {
            "legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "multi", "sort": "none"},
        },
        "targets": targets,
    }


panels = []

# ---------------- Row: llama-swap & Models ----------------
r = Row(panels, "llama-swap & Models", 0)
r.add(stat("llama-swap Up", 0, 0, "llama_swap_up",
           thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}]))
r.add(stat("Models Up", 4, 0, "count(llama_swap_model_up == 1)"))
r.add(stat("Scrape Duration p95", 8, 0,
           'histogram_quantile(0.95, sum(rate(llama_swap_scrape_duration_seconds_bucket[5m])) by (le))',
           unit="s", thresholds=[{"color": "green", "value": None}, {"color": "yellow", "value": 0.5}, {"color": "red", "value": 2}]))
r.add(stat("Scrape Errors /s", 12, 0, "rate(llama_swap_scrape_errors_total[5m])",
           thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 0.001}]))
r.add({
    "datasource": DS,
    "fieldConfig": {
        "defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "inspect": False}},
        "overrides": [],
    },
    "gridPos": {"h": 8, "w": 8, "x": 16, "y": 0},
    "id": nid(),
    "options": {"showHeader": True, "sortBy": [{"desc": False, "displayName": "Model"}]},
    "title": "Model Inventory (model / state / upstream)",
    "type": "table",
    "targets": [{"datasource": DS, "expr": "llama_swap_model_info", "format": "table", "instant": True, "refId": "A"}],
})
y = r.end()

# ---------------- Row: Tokens & Throughput (ninfer engine) ----------------
r = Row(panels, "Tokens & Throughput (ninfer engine via llama-swap)", y)
r.add(stat("Total Decoded Tokens", 0, 0, "sum(ninfer_engine_committed_decode_tokens_total)"))
r.add(stat("Total Prefill Tokens", 4, 0, "sum(ninfer_engine_computed_prefill_tokens_total)"))
r.add(stat("Max Context Tokens", 8, 0, "max(ninfer_max_context_tokens)"))
r.add(stat("Running Requests", 12, 0, "sum(ninfer_engine_running_requests)"))
r.add(stat("Waiting Requests", 16, 0, "sum(ninfer_engine_waiting_requests)"))
r.add(stat("Engine Uptime", 20, 0, "max(ninfer_uptime_seconds)", unit="s"))
r.add(ts(
    "Token Throughput (tokens/s, prefill vs decode)", 0, 4,
    [
        tgt("sum(rate(ninfer_engine_computed_prefill_tokens_total[5m])) by (model)", "{{model}} prefill"),
        tgt("sum(rate(ninfer_engine_committed_decode_tokens_total[5m])) by (model)", "{{model}} decode", ref="B"),
    ],
    unit="cps",
))
r.add(ts(
    "Engine Requests (running / waiting / prefilling)", 12, 4,
    [
        tgt("sum(ninfer_engine_running_requests) by (model)", "{{model}} running"),
        tgt("sum(ninfer_engine_waiting_requests) by (model)", "{{model}} waiting", ref="B"),
        tgt("sum(ninfer_engine_prefilling_requests) by (model)", "{{model}} prefilling", ref="C"),
    ],
))
r.add(ts(
    "HTTP Requests by Status (req/s)", 0, 12,
    [tgt('sum(rate(ninfer_http_requests_total[5m])) by (status, model)', "{{status}} {{model}}")],
    unit="reqps",
))
r.add(ts(
    "Speculative Decoding (accepted vs draft tokens/s)", 12, 12,
    [
        tgt("sum(rate(ninfer_speculative_accepted_tokens_total[5m])) by (model)", "{{model}} accepted"),
        tgt("sum(rate(ninfer_speculative_draft_tokens_total[5m])) by (model)", "{{model}} draft", ref="B"),
    ],
    unit="cps",
))
y = r.end()

# ---------------- Row: GPU (DCGM + exporter) ----------------
r = Row(panels, "GPU (DCGM + exporter)", y)
r.add(ts(
    "GPU Core Utilization (%)", 0, 0,
    [tgt('DCGM_FI_DEV_GPU_UTIL', "{{modelName}}")],
    unit="percent", min_=0, max_=100,
))
r.add(ts(
    "VRAM Used / Free (MiB)", 12, 0,
    [
        tgt('DCGM_FI_DEV_FB_USED / 1024', "{{modelName}} used"),
        tgt('DCGM_FI_DEV_FB_FREE / 1024', "{{modelName}} free", ref="B"),
    ],
    unit="decmbytes",
))
r.add(ts(
    "GPU Power (W)", 0, 8,
    [tgt('DCGM_FI_DEV_POWER_USAGE', "{{modelName}}")],
    unit="watt",
))
r.add(ts(
    "GPU Temperatures (C)", 12, 8,
    [
        tgt('DCGM_FI_DEV_GPU_TEMP', "{{modelName}} core"),
        tgt('DCGM_FI_DEV_MEMORY_TEMP', "{{modelName}} memory", ref="B"),
    ],
    unit="celsius",
))
r.add(stat("Fan Speed", 0, 16, "avg(llamaswap_gpu_fan_speed_percent)", unit="percent", w=6))
r.add(stat("XID Errors", 6, 16, "max(DCGM_FI_DEV_XID_ERRORS)",
           thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 1}], w=6))
r.add(ts(
    "GPU Pipeline Workload (%)", 12, 16,
    [
        tgt('DCGM_FI_DEV_GPU_UTIL', "{{modelName}} compute"),
        tgt('DCGM_FI_DEV_MEM_COPY_UTIL', "{{modelName}} memory copy", ref="B"),
        tgt('DCGM_FI_DEV_ENC_UTIL', "{{modelName}} encode", ref="C"),
        tgt('DCGM_FI_DEV_DEC_UTIL', "{{modelName}} decode", ref="D"),
    ],
    unit="percent",
))
r.add(ts(
    "GPU Clocks (MHz)", 0, 24,
    [
        tgt('DCGM_FI_DEV_SM_CLOCK', "{{modelName}} SM"),
        tgt('DCGM_FI_DEV_MEM_CLOCK', "{{modelName}} memory", ref="B"),
    ],
    unit="hzm",
))
r.add(ts(
    "Energy Consumed (Wh/h)", 12, 24,
    [tgt('DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION / 3600000', "{{modelName}}")],
    unit="wh",
))
r.add(stat("PCIe Replay Counter", 0, 32, "max(DCGM_FI_DEV_PCIE_REPLAY_COUNTER)",
           thresholds=[{"color": "green", "value": None}, {"color": "yellow", "value": 1}, {"color": "red", "value": 100}], w=6, h=8))
r.add(ts(
    "Engine Memory Arena (used / peak, by arena)", 6, 32,
    [
        tgt('sum(ninfer_memory_arena_bytes{state="used"}) by (arena)', "{{arena}} used"),
        tgt('sum(ninfer_memory_arena_bytes{state="peak"}) by (arena)', "{{arena}} peak", ref="B"),
    ],
    unit="bytes",
))
y = r.end()

# ---------------- Row: Host ----------------
r = Row(panels, "Host (llama-swap-exporter hostinfo)", y)
r.add(ts(
    "Host RAM (GiB)", 0, 0,
    [
        tgt('llamaswap_memory_used_bytes / 1073741824', "used"),
        tgt('llamaswap_memory_free_bytes / 1073741824', "free", ref="B"),
        tgt('llamaswap_memory_total_bytes / 1073741824', "total", ref="C"),
    ],
    unit="gbytes",
))
r.add(ts(
    "Host Swap (GiB)", 12, 0,
    [
        tgt('llamaswap_swap_used_bytes / 1073741824', "used"),
        tgt('llamaswap_swap_total_bytes / 1073741824', "total", ref="B"),
    ],
    unit="gbytes",
))
r.add(ts(
    "Load Average", 0, 8,
    [
        tgt('llamaswap_load_average{interval="1m"}', "1m"),
        tgt('llamaswap_load_average{interval="5m"}', "5m", ref="B"),
        tgt('llamaswap_load_average{interval="15m"}', "15m", ref="C"),
    ],
))
r.add(ts(
    "Network (B/s)", 12, 8,
    [
        tgt('rate(llamaswap_network_bytes_total{direction="recv"}[5m]) by (interface)', "{{interface}} recv"),
        tgt('rate(llamaswap_network_bytes_total{direction="sent"}[5m]) by (interface)', "{{interface}} sent", ref="B"),
    ],
    unit="Bps",
))
r.add(ts(
    "CPU Utilization (%) - all cores", 0, 16,
    [
        tgt('llamaswap_cpu_util_percent', "core {{core}}"),
    ],
    unit="percent", min_=0, max_=100, fill=30,
))
r.add(ts(
    "CPU Utilization (%) - overall avg", 12, 16,
    [
        tgt('avg(llamaswap_cpu_util_percent)', "all cores avg"),
        tgt('max(llamaswap_cpu_util_percent)', "hottest core", ref="B"),
    ],
    unit="percent", min_=0, max_=100,
))
y = r.end()

dashboard = {
    "annotations": {
        "list": [
            {
                "builtIn": 1,
                "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                "enable": True,
                "hide": True,
                "iconColor": "rgba(0, 211, 255, 1)",
                "name": "Annotations & Alerts",
                "type": "dashboard",
            }
        ]
    },
    "description": (
        "Unified llama-swap stack observability: exporter health, ninfer engine "
        "tokens/throughput (proxied via llama-swap /metrics, job llama-swap-metrics), "
        "GPU (DCGM), and host metrics. Consolidates: llama_swap_exporter.json, "
        "llamaswap.json, llama-swap-full-observability, llamacpp-exact-metrics "
        "(llamacpp:* series went dead after the ninfer backend consolidation fe5d6ec). "
        "Deep engine internals (KV cache, latency percentiles, speculative detail, "
        "HTTP surface) live in 'NInfer - Inference Engine'."
    ),
    "editable": True,
    "fiscalYearStartMonth": 0,
    "graphTooltip": 1,
    "id": None,
    "links": [],
    "liveNow": False,
    "panels": panels,
    "refresh": "30s",
    "schemaVersion": 42,
    "tags": ["llama-swap", "ninfer", "dcgm", "prometheus"],
    "templating": {
        "list": [
            {
                "current": {"selected": False, "text": "Prometheus", "value": "Prometheus"},
                "hide": 0,
                "includeAll": False,
                "label": "Data Source",
                "multi": False,
                "name": "DS_PROMETHEUS",
                "options": [],
                "query": "prometheus",
                "refresh": 1,
                "regex": "",
                "skipUrlSync": False,
                "type": "datasource",
            }
        ]
    },
    "time": {"from": "now-3h", "to": "now"},
    "timepicker": {},
    "timezone": "browser",
    "title": "llama-swap Full Observability",
    "uid": "llama-swap-full-observability",
    "version": 1,
    "weekStart": "",
}

out = "grafana/dashboards/llama-swap.json"
with open(out, "w") as f:
    json.dump(dashboard, f, indent=2)
    f.write("\n")
n_rows = sum(1 for p in panels if p["type"] == "row")
print(f"wrote {out}: {len(panels)} top-level panels ({n_rows} rows, {len(panels) - n_rows} content panels)")