#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker/docker-compose.yml"

case "${1:-}" in
  build)
    docker-compose -f "$COMPOSE_FILE" build
    ;;
  up)
    docker-compose -f "$COMPOSE_FILE" up -d
    ;;
  down)
    docker-compose -f "$COMPOSE_FILE" down
    ;;
  restart)
    docker-compose -f "$COMPOSE_FILE" down
    docker-compose -f "$COMPOSE_FILE" up -d
    ;;
  logs)
    docker-compose -f "$COMPOSE_FILE" logs -f
    ;;
  logs-api)
    docker-compose -f "$COMPOSE_FILE" logs -f api
    ;;
  logs-frontend)
    docker-compose -f "$COMPOSE_FILE" logs -f frontend
    ;;
  test)
    docker-compose -f "$COMPOSE_FILE" exec api pytest tests/ -v
    ;;
  backfill)
    shift
    docker-compose -f "$COMPOSE_FILE" exec api python -m app.management backfill "$@"
    ;;
  *)
    echo "Usage: $0 {build|up|down|restart|logs|logs-api|logs-frontend|test|backfill [TICKER ...]}"
    exit 1
    ;;
esac
