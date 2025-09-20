import requests

PROMETHEUS_URL = 'https://prometheus.domain.com/api/v1/query'

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

    for instance in sorted(all_instances):
        node_name = instance_to_job.get(instance, instance)
        ip = extract_ip(instance)

        cores = cpu_cores.get(instance, (0,))[0]
        idle_cpu = cpu_idle.get(instance, (0,))[0]
        used_cpu = 100 - idle_cpu if idle_cpu else 0

        mem_t = mem_total.get(instance, (0,))[0]
        mem_a = mem_avail.get(instance, (0,))[0]
        mem_used = mem_t - mem_a if mem_t and mem_a else 0

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

        if instance in disk_total:
            for mountpoint, total_bytes in disk_total[instance].items():
                free_bytes = disk_free.get(instance, {}).get(mountpoint, 0)
                used_bytes = total_bytes - free_bytes
                report_lines.append(f"  Mountpoint: {mountpoint}")
                report_lines.append(f"    Total: {bytes_to_gb(total_bytes):.2f} GB")
                report_lines.append(f"    Used: {bytes_to_gb(used_bytes):.2f} GB")
                report_lines.append(f"    Free: {bytes_to_gb(free_bytes):.2f} GB")
        else:
            report_lines.append("  No disk data available")

        report_lines.append("-" * 40)

        report_text = "\n".join(report_lines)

        # Write to file
        write_node_report_to_file(node_name, report_text)

if __name__ == "__main__":
    main()
