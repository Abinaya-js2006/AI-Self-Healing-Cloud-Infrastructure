# Limitations and Future Enhancements

## Implemented in this package
- Actual local host CPU, memory, and disk usage via `psutil`.
- Active HTTP(S) endpoint checks with response time and availability/error results.
- Simulated CPU/memory/disk/error metrics for demo service records.
- Random Forest model trained and evaluated on generated synthetic labels.
- A safe simulated recovery adapter with post-recovery threshold verification.

## Limitations
- Local host metrics describe the computer running Flask, not remote servers.
- HTTP checks measure availability and response time only. Remote CPU/memory/disk metrics require an agent, Prometheus/CloudWatch integration, or provider API.
- The default recovery adapter changes demo records only. It does not restart a real process, Docker container, VM, or cloud instance.
- AI model scores are educational estimates because training labels are synthetic; they are not calibrated on real failure incidents.
- The demo login and development configuration are not an enterprise identity or production deployment solution. Use HTTPS, strong secrets, CSRF protections, least privilege, audit retention, and proper secret management before deployment.

## Future work
- Add a strictly allowlisted Docker or cloud-provider recovery adapter.
- Add Prometheus/CloudWatch metrics and a service-side telemetry agent.
- Train and validate on real historical incidents and monitor model drift.
- Add notification integrations, role-based access control, deployment pipelines, and production-grade observability.
