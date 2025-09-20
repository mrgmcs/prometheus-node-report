# Prometheus Node Resource Reporter

This Python script connects to a Prometheus server, queries node-level resource metrics (CPU, memory, disk), and generates per-node reports showing usage and availability. Each node's report is saved to a separate text file.

## Features

- Fetches CPU cores, CPU usage %, memory total/used/free, and disk usage per mountpoint for each node.
- Outputs nicely formatted text reports per node.
- Saves each node's report to a separate text file named node_<node_name>.txt.
- Extracts IP addresses and friendly node names from Prometheus labels.

## Requirements

- Python 3.6 or higher
- requests Python library (pip install requests)
- Access to Prometheus HTTP API with node exporter metrics

## Installation

1. Clone or download this repository (or place the script on your machine).
2. Install dependencies:

pip install requests

## Configuration

Edit the script file (e.g. prometheus_node_reporter.py) and update the PROMETHEUS_URL variable to point to your Prometheus server API endpoint:

PROMETHEUS_URL = 'http://your-prometheus-server:9090/api/v1/query'

Make sure the URL is accessible from the machine running the script.

## Usage

Run the script using Python 3:

python3 prometheus_node_reporter.py

The script will generate a report for each node found in Prometheus metrics and save it as a text file named like:

reports/node_<node_name>.txt

in the current directory.

## Sample Report Output

Example content inside a node report file:

Node: platform-prod-ir-1 (IP: 62.60.215.160)
 CPU cores: 8
 CPU used: 35.25%
 CPU free: 64.75%
 Memory total: 31.25 GB
 Memory used: 15.40 GB
 Memory free: 15.85 GB
 Disks:
  Mountpoint: /
    Total: 500.00 GB
    Used: 320.00 GB
    Free: 180.00 GB
----------------------------------------

## Notes

- Ensure your Prometheus server collects node_exporter metrics.
- The script assumes the standard Prometheus metric names (node_cpu_seconds_total, node_memory_MemTotal_bytes, etc.).
- The disk section reports each mountpoint separately with total, used, and free space.
- If the ./reports/ directory is used for output, make sure it exists or modify the script accordingly.

## Troubleshooting

- Connection errors: Verify PROMETHEUS_URL is correct and accessible from your machine.
- Missing metrics: Ensure Prometheus is scraping your node exporters and metrics are available.
- Permissions: Ensure you have write permissions in the output directory.

