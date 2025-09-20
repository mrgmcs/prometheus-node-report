import requests

# PROMETHEUS_URL = "https://prom.karizmastudios.org/api/v1/query"
PROMETHEUS_URL = "https://prom.karizmastudios.org/api/v1/query"

def query_prometheus(query):
    response = requests.get(PROMETHEUS_URL, params={'query': query})
    response.raise_for_status()
    return response.json()['data']['result']

def bytes_to_gb(b):
    return b / (1024 ** 3)

def extract_ip(instance):
    # instance format: "IP:port"
    return instance.split(':')[0]

def get_metric_data(query):
    """
    Returns dict: {instance: (value, labels_dict)}
    """
    results = query_prometheus(query)
    data = {}
    for item in results:
        labels = item['metric']
        instance = labels.get('instance')
        if instance:
            value = float(item['value'][1])
            data[instance] = (value, labels)
    return data

def get_instance_to_job_map():
    """
    Builds a mapping from instance -> job label (node friendly name)
    """
    query = 'node_memory_MemTotal_bytes'
    results = query_prometheus(query)
    mapping = {}
    for item in results:
        labels = item['metric']
        instance = labels.get('instance')
        job = labels.get('job', instance)
        if instance:
            mapping[instance] = job
    return mapping

def get_disk_data():
    """
    Queries disk total and free bytes grouped by instance and mountpoint.

    Returns two nested dicts:
      disk_total[instance][mountpoint] = total_bytes
      disk_free[instance][mountpoint] = free_bytes
    """
    total_query = 'node_filesystem_size_bytes'
    free_query = 'node_filesystem_free_bytes'

    total_results = query_prometheus(total_query)
    free_results = query_prometheus(free_query)

    disk_total = {}
    disk_free = {}

    for item in total_results:
        labels = item['metric']
        instance = labels.get('instance')
        mount = labels.get('mountpoint')
        if instance and mount:
            disk_total.setdefault(instance, {})[mount] = float(item['value'][1])

    for item in free_results:
        labels = item['metric']
        instance = labels.get('instance')
        mount = labels.get('mountpoint')
        if instance and mount:
            disk_free.setdefault(instance, {})[mount] = float(item['value'][1])

    return disk_total, disk_free

def write_node_report_to_file(node_name, report_text):
    # Sanitize filename (remove spaces or special chars)
    safe_name = node_name.replace(' ', '_').replace('/', '_')
    filename = f"node_{safe_name}.txt"
    with open(f'./reports/{filename}', 'w') as f:
        f.write(report_text)
    print(f"Written report for {node_name} to {filename}")

def report_nodes_with_free_resources(nodes_data, cpu_free_threshold=40, mem_free_threshold=40, disk_free_threshold=40):
    """
    nodes_data: dict keyed by node name, each value is dict with keys:
        - cpu_free_percent (float)
        - mem_total (float in GB)
        - mem_free (float in GB)
        - disks: list of dicts, each with keys: mountpoint, total_gb, free_gb
    Thresholds are percentages for free CPU, memory, and disk space.
    
    Prints summary of nodes that have >= thresholds free resources.
    """
    print("\nNodes with more than {}% CPU free, {}% Memory free, and {}% Disk free:\n".format(cpu_free_threshold, mem_free_threshold, disk_free_threshold))
    
    for node, data in nodes_data.items():
        cpu_free = data.get('cpu_free_percent', 0)
        mem_total = data.get('mem_total', 0)
        mem_free = data.get('mem_free', 0)
        mem_free_pct = (mem_free / mem_total * 100) if mem_total else 0
        
        # Check disk free percentages per mountpoint
        disks = data.get('disks', [])
        disks_ok = False
        for disk in disks:
            total = disk.get('total_gb', 0)
            free = disk.get('free_gb', 0)
            free_pct = (free / total * 100) if total else 0
            if free_pct >= disk_free_threshold:
                disks_ok = True
                break
        
        if cpu_free >= cpu_free_threshold and mem_free_pct >= mem_free_threshold and disks_ok:
            print(f"Node: {node}")
            print(f"  CPU free: {cpu_free:.2f}%")
            print(f"  Memory free: {mem_free:.2f} GB ({mem_free_pct:.2f}%)")
            print("  Disk(s) with sufficient free space:")
            for disk in disks:
                total = disk.get('total_gb', 0)
                free = disk.get('free_gb', 0)
                free_pct = (free / total * 100) if total else 0
                if free_pct >= disk_free_threshold:
                    print(f"    Mountpoint: {disk.get('mountpoint')}, Free: {free:.2f} GB ({free_pct:.2f}%)")
            print("-" * 40)

def main():
    cpu_idle_query = 'avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100'
    cpu_cores_query = 'count(node_cpu_seconds_total{mode="user"}) by (instance)'
    mem_total_query = 'node_memory_MemTotal_bytes'
    mem_avail_query = 'node_memory_MemAvailable_bytes'

    # Query metrics
    cpu_idle = get_metric_data(cpu_idle_query)
    cpu_cores = get_metric_data(cpu_cores_query)
    mem_total = get_metric_data(mem_total_query)
    mem_avail = get_metric_data(mem_avail_query)
    disk_total, disk_free = get_disk_data()

    # Map instance -> friendly node name (job label)
    instance_to_job = get_instance_to_job_map()

    # Union of all instances seen across metrics
    all_instances = set(cpu_idle) | set(cpu_cores) | set(mem_total) | set(mem_avail) | set(disk_total) | set(disk_free)

    nodes_data = {}

    for instance in sorted(all_instances):
        node_name = instance_to_job.get(instance, instance)
        ip = extract_ip(instance)

        cores = cpu_cores.get(instance, (0,))[0]
        idle_cpu = cpu_idle.get(instance, (0))[0]
        used_cpu = 100 - idle_cpu if idle_cpu else 0

        mem_t = mem_total.get(instance, (0,))[0]
        mem_a = mem_avail.get(instance, (0,))[0]
        mem_used = mem_t - mem_a if mem_t and mem_a else 0

        disks_list = []
        if instance in disk_total:
            for mountpoint, total_bytes in disk_total[instance].items():
                free_bytes = disk_free.get(instance, {}).get(mountpoint, 0)
                used_bytes = total_bytes - free_bytes
                disks_list.append({
                    'mountpoint': mountpoint,
                    'total_gb': bytes_to_gb(total_bytes),
                    'used_gb': bytes_to_gb(used_bytes),
                    'free_gb': bytes_to_gb(free_bytes),
                })
        else:
            disks_list = []

        report_lines = [
            f"Node: {node_name} (IP: {ip})",
            f" CPU cores: {int(cores)}",
            f" CPU used: {used_cpu:.2f}%",
            f" CPU free: {idle_cpu:.2f}%",
            f" Memory total: {bytes_to_gb(mem_t):.2f} GB",
            f" Memory used: {bytes_to_gb(mem_used):.2f} GB",
            f" Memory free: {bytes_to_gb(mem_a):.2f} GB",
            " Disks:",
        ]

        if disks_list:
            for d in disks_list:
                report_lines.append(f"  Mountpoint: {d['mountpoint']}")
                report_lines.append(f"    Total: {d['total_gb']:.2f} GB")
                report_lines.append(f"    Used: {d['used_gb']:.2f} GB")
                report_lines.append(f"    Free: {d['free_gb']:.2f} GB")
        else:
            report_lines.append("  No disk data available")

        report_lines.append("-" * 40)

        report_text = "\n".join(report_lines)

        # Write to file
        write_node_report_to_file(node_name, report_text)

        # Store data for filtering
        nodes_data[node_name] = {
            'cpu_free_percent': idle_cpu,
            'mem_total': bytes_to_gb(mem_t),
            'mem_free': bytes_to_gb(mem_a),
            'disks': disks_list,
        }

    # Report nodes with more than 40% free resources
    report_nodes_with_free_resources(nodes_data, cpu_free_threshold=40, mem_free_threshold=40, disk_free_threshold=40)

if __name__ == "__main__":
    main()

