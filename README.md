# fencefixer

This is a network testing tool that executes iPerf and ping tests and uploads the results to InfluxDB. This makes it easy to query and visualize your network stats with Grafana.

Metrics captured:
  - TCP throughput
  - TCP retransmissions
  - UDP throughput
  - UDP packet loss
  - UDP jitter
  - ICMP latency

Required environment variables:
```bash
INFLUX_URL=
INFLUX_ORG=
INFLUX_BUCKET=
INFLUX_TOKEN=
```
Specify targets in your config.yaml file

optional docker-compose.yml content:
```bash
services:
  fencefixer:
    image: ghcr.io/concrete-lasso/fencefixer:main
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./app/config.yaml:/app/config.yaml:ro
```
Notes:
- Targets must be running iPerf server to execute the iPerf tests
- Ensure your InfluxDB bucket is created before starting the container
- ICMP max value is set at 400, if this value appears in your results it indicates a timeout
