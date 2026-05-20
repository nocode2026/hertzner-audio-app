.PHONY: deploy logs logs-worker logs-api shell-api shell-worker restart prune status

deploy:
	docker compose pull
	docker compose up -d --remove-orphans
	docker image prune -f

restart:
	docker compose restart api worker

logs:
	docker compose logs -f --tail=100

logs-api:
	docker compose logs -f --tail=100 api

logs-worker:
	docker compose logs -f --tail=100 worker

logs-nginx:
	docker compose logs -f --tail=100 nginx

shell-api:
	docker compose exec api bash

shell-worker:
	docker compose exec worker bash

shell-redis:
	docker compose exec redis redis-cli

status:
	docker compose ps
	@echo ""
	@echo "=== Disk usage ==="
	@df -h /opt/audio-app 2>/dev/null || df -h .
	@echo ""
	@echo "=== Volume sizes ==="
	@docker system df -v | grep audio-app || true

prune:
	docker image prune -f
	docker volume prune -f --filter label!=keep
