import json
import os
import subprocess
import time
from datetime import datetime, timezone
import yaml
import ping3
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

CONFIG_FILE = "/app/config.yaml"

# Environment Variables
URL = os.getenv("INFLUX_URL", "http://influxdb:8086")
TOKEN = os.environ["INFLUX_TOKEN"]
ORG = os.environ["INFLUX_ORG"]
BUCKET = os.environ["INFLUX_BUCKET"]
NETWORK = os.getenv("NETWORK", "default_network")

# Initialize InfluxDB Client
client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

def load_config():
    """
    Load and parse the YAML config file
    Return parsed dict is successful, or None if syntax error occurs
    """
    if not os.path.exists((CONFIG_FILE)):
        print(f"[CONFIG ERROR] Configuration file not found at {CONFIG_FILE}:")
        return None

    try:
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as exc:
        print("\n" + "="*60)
        print("[CONFIG ERROR] Failed to parse config.yaml due to syntax error")
        print(f"Details: {exc}")
        print("="*60 + "\n")
        return None
    except Exception as e:
        print(f"[CONFIG ERROR] Unexpected error loading config {e}")
        return None

def run_iperf_test(test):
    # Base command structure
    cmd = [
        "iperf3",
        "-c", test["host"],
        "-J",
        "-t", str(test.get("duration", 10))
    ]
    
    # NEW: Check for custom port parameter
    if "port" in test:
        cmd.extend(["-p", str(test["port"])])
    
    # Setup Protocol parameters
    protocol = test.get("protocol", "tcp")
    if protocol == "udp":
        cmd.extend(["-u", "-b", test.get("bandwidth", "100M")])
    if "streams" in test:
        cmd.extend(["-P", str(test["streams"])])

    print(f"Running iperf3: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=test.get("duration", 10) + 15
        )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            end = data.get("end", {})
            
            point = (
                Point("iperf")
                .tag("destination", test["host"])
                .tag("protocol", protocol)
                .tag("test_name", test["name"])
                .tag("network", NETWORK)
            )
            
            if protocol == "tcp":
                try:
                    point.field("tcp_download_bps", float(end["sum_received"]["bits_per_second"]))
                    point.field("tcp_upload_bps", float(end["sum_sent"]["bits_per_second"]))
                    point.field("tcp_retransmits", int(end["sum_sent"]["retransmits"]))
                except KeyError as e:
                    print(f"Parsing error (TCP data missing): {e}")
                    return
            else:
                try:
                    point.field("udp_throughput_bps", float(end["sum_received"]["bits_per_second"]))
                    point.field("udp_jitter_ms", float(end["sum"]["jitter_ms"]))
                    point.field("udp_lost_percent", float(end["sum"]["lost_percent"]))
                    point.field("udp_lost_packets", int(end["sum"]["lost_packets"]))
                except KeyError as e:
                    print(f"Parsing error (UDP data missing): {e}")
                    return

            write_api.write(bucket=BUCKET, org=ORG, record=point)
            print(f"Successfully logged iperf3 result for {test['name']} to InfluxDB.")
            
        else:
            print(f"iperf3 Error: {result.stderr}")
            
    except Exception as e:
        print(f"iperf3 Execution Error: {e}")

def run_icmp_test(test):
    host = test.get("host")
    count = test.get("count", 4) # Default to 4 packets if not specified
    test_name = test.get("name")
    
    print(f"Running ICMP ping to {host} ({count} packets)...")
    results = []
    
    for _ in range(count):
        # delay in ms, or None if timeout
        delay = ping3.ping(host, unit='ms')
        if delay is not None:
            results.append(delay)
        else:
            print(f"Connection to {host} failed (timeout)")
            results.append(400.0) # if ICMP times out, use 400ms as value to avoid type conflict in DB
            
    avg_delay = sum(results) / len(results)
    max_delay = max(results)
    min_delay = min(results)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    
    try:
        point = (
            Point("icmp_tester")
            .tag("protocol", "icmp")
            .tag("test_name", test_name)
            .tag("network", NETWORK)
        )
        point.field("target_host", host)
        point.field("avg_delay", avg_delay)
        point.field("max_delay", max_delay)
        point.field("min_delay", min_delay)
        point.field("icmp_packet_count", count)
        point.field("execution_time", timestamp)
        
        write_api.write(bucket=BUCKET, org=ORG, record=point)
        print(f"Successfully logged ICMP result for {test_name} to InfluxDB.")
    except Exception as e:
        print(f"ICMP Logging Error: {e}")

if __name__ == "__main__":
    while True:
        try:
            cfg = load_config()

            # If config load failed, wait 10s and try again
            if cfg is None:
                print("Config loading failed. Retrying in 10 seconds...")
                time.sleep(10)
                continue
            try:
                for test in cfg.get("tests", []):
                    protocol = test.get("protocol", "tcp").lower()
                    if protocol == "icmp":
                        run_icmp_test(test)
                    else:
                        run_iperf_test(test)
            
                # Use general interval default of 60 seconds if not specified in config
                time.sleep(cfg.get("interval", 60))
        except Exception as e:
            print(f"Global Loop Error: {e}")
            time.sleep(10) # Prevent tight CPU spin in case of continuous config parse failures
