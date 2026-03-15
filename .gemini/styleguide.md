# CrunchTools Web Application Code Review Standards

## Host Directory Convention
- All container data lives under `/srv/<container-name>/`
- Three subdirectories: `code/` (`:ro,Z`), `config/` (`:ro,Z`), `data/` (`:Z`)
- No hardcoded credentials — use environment files or mounted secrets

## Containerfile
- Use `Containerfile`, not `Dockerfile`
- Prefer multi-stage builds when compile-time deps shouldn't be in the final image
- systemd unit files and init scripts go in `rootfs/` directory
- Required LABELs: `maintainer`, `description`, plus OCI labels

## Data Persistence
- Database init MUST use a oneshot systemd service with proper After/Before ordering
- VOLUME declarations for database and upload directories
- Document backup strategy for `/srv/<name>/data/`

## Runtime Configuration
- App config loaded from environment files via systemd `EnvironmentFile=`
- Runtime configs bind-mounted from host `config/` directory
- No hardcoded database passwords, API keys, or secrets

## Monitoring
- Every HTTP service needs a Zabbix web scenario
- Every database needs a TCP port check
- Multi-service containers need monitoring for each service

## Versioning
- Semantic Versioning 2.0.0
- AI-assisted commits MUST include `Co-Authored-By` trailer
